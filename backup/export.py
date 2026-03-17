"""
Export routes — download payroll data as CSV or Excel
GET /export/employees            → employees CSV
GET /export/payroll-history      → pay run history CSV
GET /export/employee-ytd         → per-employee YTD CSV (for W-2 prep)
GET /export/pay-run/{id}         → single pay run detail CSV
GET /export/time-entries         → time entries CSV
"""
import csv
import io
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import Employee, PayRun, PayRunItem, PayPeriod, TimeEntry
from utils.auth import get_current_user

router = APIRouter(prefix="/export", tags=["export"])


def csv_response(rows: list[dict], filename: str) -> Response:
    """Build a CSV Response from a list of dicts."""
    if not rows:
        return Response(content="No data\n", media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/employees")
async def export_employees(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(Employee).where(Employee.company_id == current_user["company_id"])
    if status:
        q = q.where(Employee.status == status)
    q = q.order_by(Employee.last_name, Employee.first_name)
    result = await db.execute(q)
    employees = result.scalars().all()

    rows = [
        {
            "employee_id": str(e.id),
            "first_name": e.first_name,
            "last_name": e.last_name,
            "email": e.email or "",
            "phone": e.phone or "",
            "hire_date": str(e.hire_date) if e.hire_date else "",
            "status": e.status,
            "pay_type": e.pay_type,
            "pay_rate": float(e.pay_rate),
            "pay_frequency": e.pay_frequency,
            "department": e.department or "",
            "job_title": e.job_title or "",
            "filing_status": e.filing_status,
            "state_code": e.state_code or "",
            "health_insurance_deduction": float(e.health_insurance_deduction or 0),
            "dental_deduction": float(e.dental_deduction or 0),
            "vision_deduction": float(e.vision_deduction or 0),
            "retirement_401k_pct": float(e.retirement_401k_pct or 0),
            "hsa_deduction": float(e.hsa_deduction or 0),
        }
        for e in employees
    ]
    return csv_response(rows, "employees.csv")


@router.get("/payroll-history")
async def export_payroll_history(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = (
        select(PayRun, PayPeriod)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(PayRun.company_id == current_user["company_id"])
    )
    if year:
        q = q.where(func.extract("year", PayPeriod.period_start) == year)
    q = q.order_by(PayPeriod.period_start.desc())
    result = await db.execute(q)
    runs = result.all()

    rows = [
        {
            "pay_run_id": str(r.PayRun.id),
            "period_start": str(r.PayPeriod.period_start),
            "period_end": str(r.PayPeriod.period_end),
            "pay_date": str(r.PayPeriod.pay_date),
            "status": r.PayRun.status,
            "employee_count": r.PayRun.employee_count,
            "total_gross": float(r.PayRun.total_gross or 0),
            "total_employee_taxes": float(r.PayRun.total_employee_taxes or 0),
            "total_employer_taxes": float(r.PayRun.total_employer_taxes or 0),
            "total_deductions": float(r.PayRun.total_deductions or 0),
            "total_net": float(r.PayRun.total_net or 0),
            "created_at": str(r.PayRun.created_at),
        }
        for r in runs
    ]
    fname = f"payroll-history-{year or 'all'}.csv"
    return csv_response(rows, fname)


@router.get("/employee-ytd")
async def export_employee_ytd(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    year = year or date.today().year
    result = await db.execute(
        select(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            Employee.department,
            Employee.job_title,
            Employee.state_code,
            Employee.filing_status,
            func.sum(PayRunItem.gross_pay).label("ytd_gross"),
            func.sum(PayRunItem.federal_income_tax).label("ytd_federal"),
            func.sum(PayRunItem.state_income_tax).label("ytd_state"),
            func.sum(PayRunItem.social_security_tax).label("ytd_ss"),
            func.sum(PayRunItem.medicare_tax).label("ytd_medicare"),
            func.sum(PayRunItem.additional_medicare_tax).label("ytd_add_medicare"),
            func.sum(PayRunItem.retirement_401k).label("ytd_401k"),
            func.sum(PayRunItem.health_insurance).label("ytd_health"),
            func.sum(PayRunItem.dental_insurance).label("ytd_dental"),
            func.sum(PayRunItem.vision_insurance).label("ytd_vision"),
            func.sum(PayRunItem.hsa).label("ytd_hsa"),
            func.sum(PayRunItem.garnishment).label("ytd_garnishment"),
            func.sum(PayRunItem.net_pay).label("ytd_net"),
        )
        .join(PayRunItem, Employee.id == PayRunItem.employee_id)
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            Employee.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
        .group_by(Employee.id, Employee.first_name, Employee.last_name,
                  Employee.department, Employee.job_title,
                  Employee.state_code, Employee.filing_status)
        .order_by(Employee.last_name, Employee.first_name)
    )
    rows_raw = result.all()

    rows = [
        {
            "employee_id": str(r.id),
            "last_name": r.last_name,
            "first_name": r.first_name,
            "department": r.department or "",
            "job_title": r.job_title or "",
            "state": r.state_code or "",
            "filing_status": r.filing_status or "",
            "ytd_gross": round(float(r.ytd_gross or 0), 2),
            "ytd_federal_income_tax": round(float(r.ytd_federal or 0), 2),
            "ytd_state_income_tax": round(float(r.ytd_state or 0), 2),
            "ytd_social_security": round(float(r.ytd_ss or 0), 2),
            "ytd_medicare": round(float(r.ytd_medicare or 0), 2),
            "ytd_additional_medicare": round(float(r.ytd_add_medicare or 0), 2),
            "ytd_401k": round(float(r.ytd_401k or 0), 2),
            "ytd_health_insurance": round(float(r.ytd_health or 0), 2),
            "ytd_dental": round(float(r.ytd_dental or 0), 2),
            "ytd_vision": round(float(r.ytd_vision or 0), 2),
            "ytd_hsa": round(float(r.ytd_hsa or 0), 2),
            "ytd_garnishment": round(float(r.ytd_garnishment or 0), 2),
            "ytd_net": round(float(r.ytd_net or 0), 2),
        }
        for r in rows_raw
    ]
    return csv_response(rows, f"employee-ytd-{year}.csv")


@router.get("/pay-run/{run_id}")
async def export_pay_run_detail(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PayRunItem, Employee)
        .join(Employee, PayRunItem.employee_id == Employee.id)
        .where(
            PayRunItem.pay_run_id == run_id,
            PayRunItem.company_id == current_user["company_id"],
        )
        .order_by(Employee.last_name, Employee.first_name)
    )
    items = result.all()

    rows = [
        {
            "last_name": r.Employee.last_name,
            "first_name": r.Employee.first_name,
            "department": r.Employee.department or "",
            "job_title": r.Employee.job_title or "",
            "pay_type": r.Employee.pay_type,
            "regular_hours": float(r.PayRunItem.regular_hours or 0),
            "overtime_hours": float(r.PayRunItem.overtime_hours or 0),
            "regular_pay": float(r.PayRunItem.regular_pay or 0),
            "overtime_pay": float(r.PayRunItem.overtime_pay or 0),
            "bonus_pay": float(r.PayRunItem.bonus_pay or 0),
            "gross_pay": float(r.PayRunItem.gross_pay or 0),
            "health_insurance": float(r.PayRunItem.health_insurance or 0),
            "retirement_401k": float(r.PayRunItem.retirement_401k or 0),
            "total_pretax_deductions": float(r.PayRunItem.total_pretax_deductions or 0),
            "federal_income_tax": float(r.PayRunItem.federal_income_tax or 0),
            "state_income_tax": float(r.PayRunItem.state_income_tax or 0),
            "social_security_tax": float(r.PayRunItem.social_security_tax or 0),
            "medicare_tax": float(r.PayRunItem.medicare_tax or 0),
            "total_employee_taxes": float(r.PayRunItem.total_employee_taxes or 0),
            "employer_social_security": float(r.PayRunItem.employer_social_security or 0),
            "employer_medicare": float(r.PayRunItem.employer_medicare or 0),
            "futa_tax": float(r.PayRunItem.futa_tax or 0),
            "total_employer_taxes": float(r.PayRunItem.total_employer_taxes or 0),
            "garnishment": float(r.PayRunItem.garnishment or 0),
            "net_pay": float(r.PayRunItem.net_pay or 0),
            "ytd_gross": float(r.PayRunItem.ytd_gross or 0),
            "ytd_net": float(r.PayRunItem.ytd_net or 0),
        }
        for r in items
    ]
    return csv_response(rows, f"pay-run-{run_id[:8]}.csv")


@router.get("/time-entries")
async def export_time_entries(
    employee_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = (
        select(TimeEntry, Employee)
        .join(Employee, TimeEntry.employee_id == Employee.id)
        .where(TimeEntry.company_id == current_user["company_id"])
    )
    if employee_id:
        q = q.where(TimeEntry.employee_id == employee_id)
    if start_date:
        q = q.where(TimeEntry.entry_date >= start_date)
    if end_date:
        q = q.where(TimeEntry.entry_date <= end_date)
    q = q.order_by(TimeEntry.entry_date.desc(), Employee.last_name)
    result = await db.execute(q)
    entries = result.all()

    rows = [
        {
            "date": str(r.TimeEntry.entry_date),
            "last_name": r.Employee.last_name,
            "first_name": r.Employee.first_name,
            "department": r.Employee.department or "",
            "entry_type": r.TimeEntry.entry_type,
            "regular_hours": float(r.TimeEntry.regular_hours or 0),
            "overtime_hours": float(r.TimeEntry.overtime_hours or 0),
            "total_hours": float((r.TimeEntry.regular_hours or 0) + (r.TimeEntry.overtime_hours or 0)),
            "approved": r.TimeEntry.approved,
            "notes": r.TimeEntry.notes or "",
        }
        for r in entries
    ]
    return csv_response(rows, "time-entries.csv")
