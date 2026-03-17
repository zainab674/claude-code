from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from models import Paystub, PayRunItem, Employee, Company, PayPeriod, PayRun
from services.pdf_generator import generate_paystub_pdf
from utils.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/paystubs", tags=["paystubs"])


@router.get("")
async def list_paystubs(
    employee_id: str = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = UUID(employee_id) if isinstance(employee_id, str) else employee_id
    
    stubs = await Paystub.find(query).sort("-created_at").limit(100).to_list()
    
    return [{"id": str(s.id), "employee_id": str(s.employee_id),
             "pay_run_id": str(s.pay_run_id), "created_at": str(s.created_at)} for s in stubs]


@router.get("/{paystub_id}")
async def get_paystub(
    paystub_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    stub = await Paystub.find_one(
        Paystub.id == paystub_id, 
        Paystub.company_id == current_user["company_id"]
    )
    if not stub:
        raise HTTPException(404, "Paystub not found")

    # Load related data using Beanie find_one/get
    item = await PayRunItem.find_one(PayRunItem.id == stub.pay_run_item_id)
    if not item:
        raise HTTPException(404, "Pay run item not found")

    emp = await Employee.find_one(Employee.id == stub.employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    company = await Company.find_one(Company.id == stub.company_id)
    if not company:
        raise HTTPException(404, "Company not found")

    run = await PayRun.find_one(PayRun.id == stub.pay_run_id)
    if not run:
        raise HTTPException(404, "Pay run not found")

    period = await PayPeriod.find_one(PayPeriod.id == run.pay_period_id)
    if not period:
        raise HTTPException(404, "Pay period not found")

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
            "gross_pay": float(getattr(item, "gross_pay", 0) or 0),
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
            "federal_income_tax": float(getattr(item, "federal_income_tax", 0) or 0),
            "state_income_tax": float(getattr(item, "state_income_tax", 0) or 0),
            "social_security_tax": float(getattr(item, "social_security_tax", 0) or 0),
            "medicare_tax": float(getattr(item, "medicare_tax", 0) or 0),
            "total_employee_taxes": float(item.total_employee_taxes or 0),
        },
        "employer_taxes": {
            "employer_social_security": float(getattr(item, "employer_social_security", 0) or 0),
            "employer_medicare": float(getattr(item, "employer_medicare", 0) or 0),
            "futa_tax": float(getattr(item, "futa_tax", 0) or 0),
            "total_employer_taxes": float(item.total_employer_taxes or 0),
        },
        "net_pay": float(item.net_pay or 0),
        "ytd": {
            "gross": float(item.ytd_gross or 0),
            "federal_tax": float(item.ytd_federal_tax or 0),
            "social_security": float(item.ytd_ss_tax or 0),
            "medicare": float(item.ytd_medicare_tax or 0),
            "net": float(item.ytd_net or 0),
        },
    }


@router.get("/{paystub_id}/download")
async def download_paystub_pdf(
    paystub_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    """Generate and stream the paystub PDF."""
    data = await get_paystub(paystub_id, current_user)

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
    stub = await Paystub.find_one(Paystub.id == paystub_id)
    if stub:
        stub.viewed_at = datetime.utcnow()
        await stub.save()

    name = f"paystub_{data['employee']['last_name']}_{data['pay_period']['period_end']}.pdf"
    return FileResponse(pdf_path, media_type="application/pdf", filename=name)
