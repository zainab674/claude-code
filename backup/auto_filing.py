"""
Automated filing reminders and W-2/941 package generator.
Runs on schedule to:
  - Generate year-end W-2 packages automatically (Jan 1)
  - Generate quarterly 941 summaries (Apr, Jul, Oct, Jan)
  - Send reminder emails to admins before each deadline

POST /auto-filing/setup          configure auto filing reminders
GET  /auto-filing/status         next scheduled actions
POST /auto-filing/run-w2/{year}  manually trigger W-2 generation
POST /auto-filing/run-941/{year}/{quarter}  manually trigger 941 summary
GET  /auto-filing/checklist/{year}   complete year-end checklist with status
"""
import uuid
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, Date, DateTime, ForeignKey, Text, select, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/auto-filing", tags=["auto-filing"])


class AutoFilingConfig(Base):
    __tablename__ = "auto_filing_configs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), unique=True)
    enabled = Column(Boolean, default=True)
    w2_auto_generate = Column(Boolean, default=True)
    w2_reminder_days_before = Column(String(10), default="30")
    filing_941_reminders = Column(Boolean, default=True)
    email_reminders = Column(Boolean, default=True)
    reminder_email = Column(String(255))
    last_w2_year_generated = Column(String(4))
    last_941_quarter = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class AutoFilingSetup(BaseModel):
    enabled: bool = True
    w2_auto_generate: bool = True
    w2_reminder_days_before: int = 30
    filing_941_reminders: bool = True
    email_reminders: bool = True
    reminder_email: Optional[str] = None


@router.post("/setup")
async def setup_auto_filing(
    body: AutoFilingSetup,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(AutoFilingConfig).where(AutoFilingConfig.company_id == current_user["company_id"])
    )
    config = result.scalar_one_or_none()
    if config:
        config.enabled = body.enabled
        config.w2_auto_generate = body.w2_auto_generate
        config.w2_reminder_days_before = str(body.w2_reminder_days_before)
        config.filing_941_reminders = body.filing_941_reminders
        config.email_reminders = body.email_reminders
        config.reminder_email = body.reminder_email
        config.updated_at = datetime.utcnow()
    else:
        config = AutoFilingConfig(
            company_id=current_user["company_id"],
            enabled=body.enabled,
            w2_auto_generate=body.w2_auto_generate,
            w2_reminder_days_before=str(body.w2_reminder_days_before),
            filing_941_reminders=body.filing_941_reminders,
            email_reminders=body.email_reminders,
            reminder_email=body.reminder_email,
        )
        db.add(config)
    await db.commit()
    return {"message": "Auto-filing configured", "enabled": body.enabled}


@router.get("/status")
async def auto_filing_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(AutoFilingConfig).where(AutoFilingConfig.company_id == current_user["company_id"])
    )
    config = result.scalar_one_or_none()
    today = date.today()
    year = today.year

    # Calculate upcoming deadlines
    deadlines = [
        {"name": "W-2 to employees",     "date": date(year, 1, 31), "form": "W-2",     "portal": "SSA BSO", "url": "https://www.ssa.gov/employer/"},
        {"name": "W-2 to SSA",           "date": date(year, 1, 31), "form": "EFW2",    "portal": "SSA BSO", "url": "https://www.ssa.gov/employer/"},
        {"name": "1099-NEC to IRS",       "date": date(year, 1, 31), "form": "1099-NEC","portal": "IRS IRIS","url": "https://www.irs.gov/filing/e-file-information-returns-with-iris"},
        {"name": "Form 941 Q1",           "date": date(year, 4, 30), "form": "941",     "portal": "EFTPS",   "url": "https://www.eftps.gov"},
        {"name": "Form 941 Q2",           "date": date(year, 7, 31), "form": "941",     "portal": "EFTPS",   "url": "https://www.eftps.gov"},
        {"name": "Form 941 Q3",           "date": date(year, 10, 31),"form": "941",     "portal": "EFTPS",   "url": "https://www.eftps.gov"},
        {"name": "Form 940 FUTA annual",  "date": date(year+1, 1, 31),"form": "940",    "portal": "EFTPS",   "url": "https://www.eftps.gov"},
        {"name": "Form 941 Q4",           "date": date(year+1, 1, 31),"form": "941",    "portal": "EFTPS",   "url": "https://www.eftps.gov"},
    ]

    upcoming = []
    for dl in deadlines:
        days_until = (dl["date"] - today).days
        if days_until >= 0:
            dl["days_until"] = days_until
            dl["status"] = "urgent" if days_until <= 7 else "upcoming" if days_until <= 30 else "future"
            dl["date"] = str(dl["date"])
            upcoming.append(dl)

    upcoming.sort(key=lambda x: x["days_until"])

    return {
        "configured": config is not None,
        "enabled": config.enabled if config else False,
        "w2_auto_generate": config.w2_auto_generate if config else False,
        "email_reminders": config.email_reminders if config else False,
        "reminder_email": config.reminder_email if config else None,
        "upcoming_deadlines": upcoming[:6],
        "next_action": upcoming[0] if upcoming else None,
    }


@router.post("/run-w2/{year}")
async def generate_w2_package(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Trigger W-2 generation for the full year and return download links."""
    from routes.w2 import get_w2_data
    data = await get_w2_data(year, db, current_user)

    return {
        "success": True,
        "year": year,
        "employee_count": data["employee_count"],
        "company": data["company"],
        "generated_at": datetime.utcnow().isoformat(),
        "downloads": {
            "w2_json": f"/w2/{year}",
            "w2_xml_efw2": f"/w2/{year}/xml",
            "ssa_upload_instructions": f"/filing/ssa-w2/{year}",
        },
        "next_steps": [
            f"Download EFW2 XML: GET /w2/{year}/xml",
            "Log into SSA BSO: https://www.ssa.gov/employer/",
            "Upload the EFW2 file to SSA",
            f"Send W-2 copies to all {data['employee_count']} employees by Jan 31",
        ],
        "ssa_bso_url": "https://www.ssa.gov/employer/",
    }


@router.post("/run-941/{year}/{quarter}")
async def generate_941_summary(
    year: int,
    quarter: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate 941 quarterly summary data."""
    if quarter not in (1, 2, 3, 4):
        raise HTTPException(400, "Quarter must be 1, 2, 3, or 4")

    quarter_months = {1: [1,2,3], 2: [4,5,6], 3: [7,8,9], 4: [10,11,12]}
    months = quarter_months[quarter]

    from models import PayRunItem, PayRun, PayPeriod
    res = await db.execute(
        select(
            func.sum(PayRunItem.gross_pay).label("gross"),
            func.sum(PayRunItem.federal_income_tax).label("federal"),
            func.sum(PayRunItem.social_security_tax).label("emp_ss"),
            func.sum(PayRunItem.medicare_tax).label("emp_med"),
            func.sum(PayRunItem.employer_social_security).label("er_ss"),
            func.sum(PayRunItem.employer_medicare).label("er_med"),
            func.sum(PayRunItem.additional_medicare_tax).label("add_med"),
            func.count(func.distinct(PayRunItem.employee_id)).label("emp_count"),
        )
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRunItem.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
            func.extract("month", PayPeriod.period_start).in_(months),
        )
    )
    row = res.first()

    gross         = float(row.gross or 0)
    federal       = float(row.federal or 0)
    emp_ss        = float(row.emp_ss or 0)
    emp_med       = float(row.emp_med or 0)
    er_ss         = float(row.er_ss or 0)
    er_med        = float(row.er_med or 0)
    add_med       = float(row.add_med or 0)
    emp_count     = row.emp_count or 0
    total_fica    = emp_ss + emp_med + er_ss + er_med + add_med
    total_941     = federal + total_fica

    quarter_labels = {1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec"}
    due_dates = {1: f"Apr 30, {year}", 2: f"Jul 31, {year}", 3: f"Oct 31, {year}", 4: f"Jan 31, {year+1}"}

    return {
        "year": year,
        "quarter": quarter,
        "period": quarter_labels[quarter],
        "due_date": due_dates[quarter],
        "employees": emp_count,
        "form_941_data": {
            "line_2_wages_tips":           round(gross, 2),
            "line_3_federal_income_tax":   round(federal, 2),
            "line_5a_ss_wages":            round(gross, 2),
            "line_5a_ss_tax":              round(emp_ss + er_ss, 2),
            "line_5c_medicare_wages":      round(gross, 2),
            "line_5c_medicare_tax":        round(emp_med + er_med, 2),
            "line_5d_additional_medicare": round(add_med, 2),
            "line_6_total_taxes":          round(total_941, 2),
        },
        "total_deposits_required": round(total_941, 2),
        "eftps_url": "https://www.eftps.gov",
        "form_941_instructions": "https://www.irs.gov/forms-pubs/about-form-941",
        "next_steps": [
            f"Log into EFTPS: https://www.eftps.gov",
            f"Make deposits on schedule (semi-weekly or monthly based on deposit schedule)",
            f"File Form 941 by {due_dates[quarter]}: https://www.irs.gov/forms-pubs/about-form-941",
            f"Total to deposit this quarter: ${round(total_941,2):,.2f}",
        ],
    }


@router.get("/checklist/{year}")
async def year_end_checklist(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Complete year-end payroll checklist with completion status."""
    from models import PayRunItem, PayRun, PayPeriod

    # Check if any payroll was run this year
    run_res = await db.execute(
        select(func.count(PayRun.id))
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    run_count = run_res.scalar() or 0

    checklist = [
        {
            "category": "Payroll",
            "task": "Run final payroll of the year",
            "status": "complete" if run_count > 0 else "pending",
            "detail": f"{run_count} pay runs completed in {year}",
        },
        {
            "category": "Reconciliation",
            "task": "Reconcile YTD totals",
            "url": f"/reconciliation/ytd-check/{year}",
            "status": "action_needed",
            "detail": "Verify sum of all pay runs matches YTD totals",
        },
        {
            "category": "W-2",
            "task": "Generate W-2 data",
            "url": f"/w2/{year}",
            "status": "action_needed",
            "detail": f"Download: GET /w2/{year}/xml",
        },
        {
            "category": "W-2",
            "task": "Upload W-2s to SSA BSO",
            "url": "https://www.ssa.gov/employer/",
            "status": "manual",
            "deadline": f"Jan 31, {year+1}",
            "detail": "Requires login to SSA Business Services Online",
        },
        {
            "category": "W-2",
            "task": "Send W-2s to employees",
            "status": "manual",
            "deadline": f"Jan 31, {year+1}",
            "detail": "Mail or email W-2 copies to all employees",
        },
        {
            "category": "1099",
            "task": "Generate 1099-NEC data",
            "url": f"/1099/report?year={year}",
            "status": "action_needed",
            "detail": f"Download: GET /1099/xml?year={year}",
        },
        {
            "category": "1099",
            "task": "File 1099-NEC with IRS IRIS",
            "url": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
            "status": "manual",
            "deadline": f"Jan 31, {year+1}",
            "detail": "Requires TCC and IRS IRIS account",
        },
        {
            "category": "1099",
            "task": "Send 1099-NEC to contractors",
            "status": "manual",
            "deadline": f"Jan 31, {year+1}",
            "detail": "Mail Copy B to each contractor paid $600+",
        },
        {
            "category": "FUTA",
            "task": "File Form 940 (annual FUTA return)",
            "url": "https://www.irs.gov/forms-pubs/about-form-940",
            "status": "manual",
            "deadline": f"Jan 31, {year+1}",
            "detail": "File via IRS e-file or tax professional",
        },
        {
            "category": "States",
            "task": "Review state withholding obligations",
            "url": f"/filing/state-ach/{year}",
            "status": "action_needed",
            "detail": "Verify all state deposits and annual reconciliation forms",
        },
        {
            "category": "Records",
            "task": "Archive payroll records",
            "status": "action_needed",
            "detail": "IRS requires 4+ years of payroll records. Export CSV: GET /export/payroll-history",
        },
    ]

    complete = sum(1 for t in checklist if t["status"] == "complete")
    manual   = sum(1 for t in checklist if t["status"] == "manual")
    pending  = sum(1 for t in checklist if t["status"] in ("action_needed", "pending"))

    return {
        "year": year,
        "summary": {
            "total_tasks": len(checklist),
            "complete": complete,
            "action_needed": pending,
            "manual_portal_steps": manual,
        },
        "checklist": checklist,
        "external_links": {
            "SSA BSO (W-2)":  "https://www.ssa.gov/employer/",
            "IRS IRIS (1099)": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
            "EFTPS (tax deposits)": "https://www.eftps.gov",
            "IRS Form 941": "https://www.irs.gov/forms-pubs/about-form-941",
            "IRS Form 940": "https://www.irs.gov/forms-pubs/about-form-940",
            "IRS Pub 15 (Circular E)": "https://www.irs.gov/publications/p15",
        },
    }
