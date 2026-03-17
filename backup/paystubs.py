from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models import Paystub, PayRunItem, Employee, Company, PayPeriod, PayRun
from services.pdf_generator import generate_paystub_pdf
from utils.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/paystubs", tags=["paystubs"])


@router.get("")
async def list_paystubs(
    employee_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(Paystub).where(Paystub.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(Paystub.employee_id == employee_id)
    q = q.order_by(Paystub.created_at.desc()).limit(100)
    result = await db.execute(q)
    stubs = result.scalars().all()
    return [{"id": str(s.id), "employee_id": str(s.employee_id),
             "pay_run_id": str(s.pay_run_id), "created_at": str(s.created_at)} for s in stubs]


@router.get("/{paystub_id}")
async def get_paystub(
    paystub_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Paystub).where(Paystub.id == paystub_id, Paystub.company_id == current_user["company_id"])
    )
    stub = result.scalar_one_or_none()
    if not stub:
        raise HTTPException(404, "Paystub not found")

    # Load related data
    item_res = await db.execute(select(PayRunItem).where(PayRunItem.id == stub.pay_run_item_id))
    item = item_res.scalar_one()

    emp_res = await db.execute(select(Employee).where(Employee.id == stub.employee_id))
    emp = emp_res.scalar_one()

    co_res = await db.execute(select(Company).where(Company.id == stub.company_id))
    company = co_res.scalar_one()

    run_res = await db.execute(select(PayRun).where(PayRun.id == stub.pay_run_id))
    run = run_res.scalar_one()

    period_res = await db.execute(select(PayPeriod).where(PayPeriod.id == run.pay_period_id))
    period = period_res.scalar_one()

    return {
        "paystub_id": str(stub.id),
        "employee": {
            "id": str(emp.id),
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "job_title": emp.job_title,
            "department": emp.department,
        },
        "company": {
            "name": company.name,
            "ein": company.ein,
            "address_line1": company.address_line1,
            "city": company.city,
            "state": company.state,
            "zip": company.zip,
        },
        "pay_period": {
            "period_start": str(period.period_start),
            "period_end": str(period.period_end),
            "pay_date": str(period.pay_date),
        },
        "earnings": {
            "regular_pay": float(item.regular_pay or 0),
            "overtime_pay": float(item.overtime_pay or 0),
            "bonus_pay": float(item.bonus_pay or 0),
            "gross_pay": float(item.gross_pay or 0),
        },
        "deductions": {
            "health_insurance": float(item.health_insurance or 0),
            "dental_insurance": float(item.dental_insurance or 0),
            "vision_insurance": float(item.vision_insurance or 0),
            "retirement_401k": float(item.retirement_401k or 0),
            "hsa": float(item.hsa or 0),
            "total_pretax": float(item.total_pretax_deductions or 0),
        },
        "taxes": {
            "federal_income_tax": float(item.federal_income_tax or 0),
            "state_income_tax": float(item.state_income_tax or 0),
            "social_security_tax": float(item.social_security_tax or 0),
            "medicare_tax": float(item.medicare_tax or 0),
            "total_employee_taxes": float(item.total_employee_taxes or 0),
        },
        "employer_taxes": {
            "employer_social_security": float(item.employer_social_security or 0),
            "employer_medicare": float(item.employer_medicare or 0),
            "futa_tax": float(item.futa_tax or 0),
            "total_employer_taxes": float(item.total_employer_taxes or 0),
        },
        "net_pay": float(item.net_pay or 0),
        "ytd": {
            "gross": float(item.ytd_gross or 0),
            "federal_tax": float(item.ytd_federal_tax or 0),
            "social_security": float(item.ytd_social_security or 0),
            "medicare": float(item.ytd_medicare or 0),
            "net": float(item.ytd_net or 0),
        },
    }


@router.get("/{paystub_id}/download")
async def download_paystub_pdf(
    paystub_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate and stream the paystub PDF."""
    data = await get_paystub(paystub_id, db, current_user)

    pdf_path = generate_paystub_pdf(
        employee=data["employee"],
        company=data["company"],
        pay_period=data["pay_period"],
        pay_item={**data["earnings"], **data["deductions"], **data["taxes"],
                  **data["employer_taxes"], **data["ytd"],
                  "net_pay": data["net_pay"],
                  "total_employer_taxes": data["employer_taxes"]["total_employer_taxes"]},
    )

    # Update viewed_at
    result = await db.execute(select(Paystub).where(Paystub.id == paystub_id))
    stub = result.scalar_one()
    stub.viewed_at = datetime.utcnow()
    await db.commit()

    name = f"paystub_{data['employee']['last_name']}_{data['pay_period']['period_end']}.pdf"
    return FileResponse(pdf_path, media_type="application/pdf", filename=name)


# ── Email paystub to employee ──────────────────────────────────
@router.post("/{paystub_id}/email")
async def email_paystub(
    paystub_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Re-send (or send for the first time) a paystub PDF to the employee's email."""
    from models import Paystub, PayRunItem, PayRun, PayPeriod, Employee, Company
    from services.pdf_generator import generate_paystub_pdf
    from services.email import send_paystub_notification

    # Load paystub
    result = await db.execute(
        select(Paystub).where(
            Paystub.id == paystub_id,
            Paystub.company_id == current_user["company_id"],
        )
    )
    stub = result.scalar_one_or_none()
    if not stub:
        raise HTTPException(status_code=404, detail="Paystub not found")

    # Load related records
    item_res = await db.execute(select(PayRunItem).where(PayRunItem.id == stub.pay_run_item_id))
    item = item_res.scalar_one_or_none()

    emp_res = await db.execute(select(Employee).where(Employee.id == stub.employee_id))
    emp = emp_res.scalar_one_or_none()

    if not emp or not emp.email:
        raise HTTPException(status_code=400, detail="Employee has no email address on file")

    run_res = await db.execute(select(PayRun).where(PayRun.id == stub.pay_run_id))
    run = run_res.scalar_one_or_none()

    pp_res = await db.execute(select(PayPeriod).where(PayPeriod.id == run.pay_period_id))
    pp = pp_res.scalar_one_or_none()

    co_res = await db.execute(select(Company).where(Company.id == current_user["company_id"]))
    company = co_res.scalar_one_or_none()

    # Generate PDF if missing
    pdf_path = stub.pdf_path
    if not pdf_path or not os.path.exists(pdf_path):
        emp_dict = {
            "id": str(emp.id), "first_name": emp.first_name, "last_name": emp.last_name,
            "job_title": emp.job_title or "", "department": emp.department or "",
            "pay_type": emp.pay_type, "pay_rate": float(emp.pay_rate or 0),
            "pay_frequency": emp.pay_frequency or "biweekly",
            "address_line1": emp.address_line1 or "", "city": emp.city or "",
            "state": emp.state or "", "zip": emp.zip or "",
        }
        co_dict = {
            "name": company.name if company else "", "ein": company.ein if company else "",
            "address_line1": company.address_line1 or "",
            "city": company.city or "", "state": company.state or "", "zip": company.zip or "",
        }
        pp_dict = {
            "period_start": str(pp.period_start) if pp else "",
            "period_end": str(pp.period_end) if pp else "",
            "pay_date": str(pp.pay_date) if pp else "",
        }
        item_dict = {k: getattr(item, k, None) for k in [
            "gross_pay","regular_pay","regular_hours","overtime_pay","overtime_hours",
            "bonus_pay","reimbursement","health_insurance","dental_insurance",
            "vision_insurance","retirement_401k","hsa","fsa","total_pretax_deductions",
            "federal_income_tax","state_income_tax","social_security_tax","medicare_tax",
            "additional_medicare_tax","total_employee_taxes","garnishment","other_post_tax",
            "total_posttax_deductions","employer_social_security","employer_medicare",
            "futa_tax","suta_tax","total_employer_taxes","net_pay",
            "ytd_gross","ytd_net","ytd_federal","ytd_state","ytd_ss","ytd_medicare","ytd_401k",
        ]} if item else {}
        pdf_path = generate_paystub_pdf(emp_dict, co_dict, pp_dict, item_dict)
        stub.pdf_path = pdf_path
        await db.commit()

    # Send email
    pay_date = str(pp.pay_date) if pp else ""
    net_pay  = float(item.net_pay or 0) if item else 0.0
    co_name  = company.name if company else ""

    sent = send_paystub_notification(
        employee_email=emp.email,
        employee_name=f"{emp.first_name} {emp.last_name}",
        company_name=co_name,
        pay_date=pay_date,
        net_pay=net_pay,
        pdf_path=pdf_path,
    )

    if not sent:
        raise HTTPException(
            status_code=503,
            detail="SMTP not configured or send failed. Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD in .env"
        )

    return {
        "success": True,
        "sent_to": emp.email,
        "employee": f"{emp.first_name} {emp.last_name}",
        "pay_date": pay_date,
        "net_pay": net_pay,
        "pdf_attached": bool(pdf_path),
    }


@router.post("/run/{pay_run_id}/email-all")
async def email_all_paystubs(
    pay_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Email all paystubs for a pay run to each employee simultaneously."""
    from models import Paystub
    result = await db.execute(
        select(Paystub).where(
            Paystub.pay_run_id == pay_run_id,
            Paystub.company_id == current_user["company_id"],
        )
    )
    stubs = result.scalars().all()
    if not stubs:
        raise HTTPException(status_code=404, detail="No paystubs found for this pay run")

    sent, failed, skipped = [], [], []
    for stub in stubs:
        try:
            r = await email_paystub(str(stub.id), db, current_user)
            sent.append(r["sent_to"])
        except HTTPException as e:
            if "no email" in e.detail.lower():
                skipped.append(str(stub.employee_id))
            else:
                failed.append(str(stub.employee_id))
        except Exception:
            failed.append(str(stub.employee_id))

    return {
        "success": True,
        "sent_count": len(sent),
        "sent_to": sent,
        "skipped_no_email": len(skipped),
        "failed": len(failed),
    }
