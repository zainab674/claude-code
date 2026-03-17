import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import User, Employee, Paystub, PayRunItem, PayRun, PayPeriod, EmployeeUserLink, PtoBalance, PtoRequest
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/self-service", tags=["self-service"])


class ContactUpdate(BaseModel):
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────
async def _get_employee_for_user(user_id: str, company_id: str) -> Employee:
    """Get the employee record linked to this user."""
    link = await EmployeeUserLink.find_one(EmployeeUserLink.user_id == UUID(user_id))
    if not link:
        raise HTTPException(403, "No employee record linked to this account. Contact HR.")

    emp = await Employee.find_one(
        Employee.id == link.employee_id,
        Employee.company_id == UUID(company_id),
    )
    if not emp:
        raise HTTPException(404, "Employee record not found")
    return emp


# ── Routes ──────────────────────────────────────────────────────
@router.get("/profile")
async def get_my_profile(
    current_user: dict = Depends(get_current_user),
):
    """Get own employee profile."""
    emp = await _get_employee_for_user(current_user["sub"], current_user["company_id"])
    return {
        "id": str(emp.id),
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "full_name": f"{emp.first_name} {emp.last_name}",
        "email": emp.email,
        "phone": emp.phone,
        "job_title": emp.job_title,
        "department": emp.department,
        "hire_date": str(emp.hire_date),
        "pay_type": emp.pay_type,
        "pay_frequency": emp.pay_frequency,
        "filing_status": emp.filing_status,
        "state_code": emp.state_code,
        "address_line1": emp.address_line1,
        "city": emp.city,
        "state": emp.state,
        "zip": emp.zip,
        # Never return pay rate or SSN to employee directly
    }


@router.put("/profile/contact")
async def update_my_contact(
    body: ContactUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Employee can update their own contact info."""
    emp = await _get_employee_for_user(current_user["sub"], current_user["company_id"])
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(emp, k, v)
    await emp.save()
    return {"message": "Contact info updated", "phone": emp.phone, "address": emp.address_line1}


@router.get("/paystubs")
async def get_my_paystubs(
    current_user: dict = Depends(get_current_user),
):
    """Get own paystub history."""
    emp = await _get_employee_for_user(current_user["sub"], current_user["company_id"])

    stubs = await Paystub.find(
        Paystub.employee_id == emp.id,
        Paystub.company_id == emp.company_id,
    ).sort("-created_at").limit(50).to_list()

    paystub_data = []
    for stub in stubs:
        item = await PayRunItem.find_one(PayRunItem.id == stub.pay_run_item_id)
        run = await PayRun.find_one(PayRun.id == stub.pay_run_id)

        period = None
        if run:
            period = await PayPeriod.find_one(PayPeriod.id == run.pay_period_id)

        paystub_data.append({
            "id": str(stub.id),
            "period_start": str(period.period_start) if period else "",
            "period_end": str(period.period_end) if period else "",
            "pay_date": str(period.pay_date) if period else "",
            "gross_pay": float(item.gross_pay or 0) if item else 0,
            "net_pay": float(item.net_pay or 0) if item else 0,
            "federal_tax": float(item.federal_income_tax or 0) if item else 0,
            "download_url": f"/paystubs/{stub.id}/download",
        })

    return {
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "total": len(paystub_data),
        "paystubs": paystub_data,
    }


@router.get("/pto")
async def get_my_pto(
    current_user: dict = Depends(get_current_user),
):
    """Get own PTO balance and request history."""
    emp = await _get_employee_for_user(current_user["sub"], current_user["company_id"])

    # Balance
    bal = await PtoBalance.find_one(PtoBalance.employee_id == emp.id)

    # Requests
    requests = await PtoRequest.find(
        PtoRequest.employee_id == emp.id
    ).sort("-created_at").limit(200).to_list()

    return {
        "balance": {
            "available_hours": float(bal.available_hours or 0) if bal else 0,
            "pending_hours": float(bal.pending_hours or 0) if bal else 0,
            "used_hours": float(bal.used_hours or 0) if bal else 0,
            "net_available": float((bal.available_hours or 0) - (bal.pending_hours or 0)) if bal else 0,
        },
        "requests": [
            {
                "id": str(r.id),
                "start_date": str(r.start_date),
                "end_date": str(r.end_date),
                "hours": float(r.hours),
                "type": r.pto_type,
                "status": r.status,
                "notes": r.notes,
            }
            for r in requests
        ],
    }


@router.get("/ytd")
async def get_my_ytd(
    current_user: dict = Depends(get_current_user),
):
    """Get own YTD earnings summary."""
    from datetime import date
    emp = await _get_employee_for_user(current_user["sub"], current_user["company_id"])
    year = date.today().year

    # Use aggregation to sum YTD values
    pipeline = [
        {"$match": {"employee_id": emp.id}},
        {
            "$lookup": {
                "from": "pay_runs",
                "localField": "pay_run_id",
                "foreignField": "_id",
                "as": "pay_run"
            }
        },
        {"$unwind": "$pay_run"},
        {"$match": {"pay_run.status": "completed"}},
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "pay_run.pay_period_id",
                "foreignField": "_id",
                "as": "pay_period"
            }
        },
        {"$unwind": "$pay_period"},
        {
            "$match": {
                "$expr": {
                    "$eq": [{"$year": "$pay_period.period_start"}, year]
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "gross": {"$sum": "$gross_pay"},
                "federal": {"$sum": "$federal_income_tax"},
                "state": {"$sum": "$state_income_tax"},
                "ss": {"$sum": "$social_security_tax"},
                "medicare": {"$sum": "$medicare_tax"},
                "retirement": {"$sum": "$retirement_401k"},
                "net": {"$sum": "$net_pay"}
            }
        }
    ]
    
    aggregation_results = await PayRunItem.aggregate(pipeline).to_list()
    row = aggregation_results[0] if aggregation_results else {}

    return {
        "year": year,
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "ytd_gross": round(float(row.get("gross", 0)), 2),
        "ytd_federal_tax": round(float(row.get("federal", 0)), 2),
        "ytd_state_tax": round(float(row.get("state", 0)), 2),
        "ytd_social_security": round(float(row.get("ss", 0)), 2),
        "ytd_medicare": round(float(row.get("medicare", 0)), 2),
        "ytd_401k": round(float(row.get("retirement", 0)), 2),
        "ytd_net": round(float(row.get("net", 0)), 2),
    }


@router.get("/onboarding")
async def get_my_onboarding(
    current_user: dict = Depends(get_current_user),
):
    """Get own onboarding checklist."""
    emp = await _get_employee_for_user(current_user["sub"], current_user["company_id"])
    # Reuse the onboarding endpoint logic (already migrated to Beanie)
    from routes.onboarding import get_onboarding
    return await get_onboarding(str(emp.id), current_user)


# ── Admin: link employee to user account ────────────────────────
@router.post("/admin/link")
async def link_employee_to_user(
    user_id: str,
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Admin: link a user account to an employee record for self-service access."""
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin required")

    existing = await EmployeeUserLink.find_one(EmployeeUserLink.user_id == UUID(user_id))
    if existing:
        raise HTTPException(409, "User already linked to an employee")

    link = EmployeeUserLink(user_id=UUID(user_id), employee_id=UUID(employee_id))
    await link.insert()
    return {"message": "Employee linked to user account", "user_id": user_id, "employee_id": employee_id}


@router.get("/admin/links")
async def list_employee_links(
    current_user: dict = Depends(get_current_user),
):
    """Admin: list all employee-user links."""
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin required")
    links = await EmployeeUserLink.find_all().to_list()
    return [{"user_id": str(l.user_id), "employee_id": str(l.employee_id)} for l in links]
