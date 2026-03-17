"""
Employee self-service portal.
Employees authenticate with their own credentials and can:
  - View their own paystubs and download PDFs
  - View their PTO balance and submit requests
  - View their onboarding checklist
  - Update their own contact info
  - View their paycheck history
  - Access their W-2 data

Separate from admin routes — employees only see their OWN data.
Auth: same JWT system, but user must have employee_id linked to their user record.
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from models import User, Employee, Paystub, PayRunItem, PayRun, PayPeriod
from utils.auth import get_current_user

router = APIRouter(prefix="/self-service", tags=["self-service"])


# ── Employee-User link model ────────────────────────────────────
class EmployeeUserLink(Base):
    """Links a User account to an Employee record for self-service."""
    __tablename__ = "employee_user_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    created_at = Column(String(50), default=lambda: datetime.utcnow().isoformat())


class ContactUpdate(BaseModel):
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────
async def _get_employee_for_user(db: AsyncSession, user_id: str, company_id: str) -> Employee:
    """Get the employee record linked to this user."""
    link_result = await db.execute(
        select(EmployeeUserLink).where(EmployeeUserLink.user_id == user_id)
    )
    link = link_result.scalar_one_or_none()
    if not link:
        raise HTTPException(403, "No employee record linked to this account. Contact HR.")

    emp_result = await db.execute(
        select(Employee).where(
            Employee.id == link.employee_id,
            Employee.company_id == company_id,
        )
    )
    emp = emp_result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee record not found")
    return emp


# ── Routes ──────────────────────────────────────────────────────
@router.get("/profile")
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get own employee profile."""
    emp = await _get_employee_for_user(db, current_user["sub"], current_user["company_id"])
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Employee can update their own contact info."""
    emp = await _get_employee_for_user(db, current_user["sub"], current_user["company_id"])
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(emp, k, v)
    await db.commit()
    await db.refresh(emp)
    return {"message": "Contact info updated", "phone": emp.phone, "address": emp.address_line1}


@router.get("/paystubs")
async def get_my_paystubs(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get own paystub history."""
    emp = await _get_employee_for_user(db, current_user["sub"], current_user["company_id"])

    result = await db.execute(
        select(Paystub).where(
            Paystub.employee_id == emp.id,
            Paystub.company_id == emp.company_id,
        ).order_by(Paystub.created_at.desc()).limit(50)
    )
    stubs = result.scalars().all()

    paystub_data = []
    for stub in stubs:
        item_res = await db.execute(
            select(PayRunItem).where(PayRunItem.id == stub.pay_run_item_id)
        )
        item = item_res.scalar_one_or_none()

        run_res = await db.execute(select(PayRun).where(PayRun.id == stub.pay_run_id))
        run = run_res.scalar_one_or_none()

        period = None
        if run:
            period_res = await db.execute(
                select(PayPeriod).where(PayPeriod.id == run.pay_period_id)
            )
            period = period_res.scalar_one_or_none()

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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get own PTO balance and request history."""
    emp = await _get_employee_for_user(db, current_user["sub"], current_user["company_id"])

    from routes.pto import PtoBalance, PtoRequest

    # Balance
    bal_res = await db.execute(
        select(PtoBalance).where(PtoBalance.employee_id == emp.id)
    )
    bal = bal_res.scalar_one_or_none()

    # Requests
    req_res = await db.execute(
        select(PtoRequest).where(
            PtoRequest.employee_id == emp.id
        ).order_by(PtoRequest.created_at.desc()).limit(20)
    )
    requests = req_res.scalars().all()

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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get own YTD earnings summary."""
    from datetime import date
    from sqlalchemy import func
    emp = await _get_employee_for_user(db, current_user["sub"], current_user["company_id"])
    year = date.today().year

    result = await db.execute(
        select(
            func.sum(PayRunItem.gross_pay).label("gross"),
            func.sum(PayRunItem.federal_income_tax).label("federal"),
            func.sum(PayRunItem.state_income_tax).label("state"),
            func.sum(PayRunItem.social_security_tax).label("ss"),
            func.sum(PayRunItem.medicare_tax).label("medicare"),
            func.sum(PayRunItem.retirement_401k).label("retirement"),
            func.sum(PayRunItem.net_pay).label("net"),
        )
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRunItem.employee_id == emp.id,
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    row = result.first()

    return {
        "year": year,
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "ytd_gross": round(float(row.gross or 0), 2),
        "ytd_federal_tax": round(float(row.federal or 0), 2),
        "ytd_state_tax": round(float(row.state or 0), 2),
        "ytd_social_security": round(float(row.ss or 0), 2),
        "ytd_medicare": round(float(row.medicare or 0), 2),
        "ytd_401k": round(float(row.retirement or 0), 2),
        "ytd_net": round(float(row.net or 0), 2),
    }


@router.get("/onboarding")
async def get_my_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get own onboarding checklist."""
    emp = await _get_employee_for_user(db, current_user["sub"], current_user["company_id"])
    # Reuse the onboarding endpoint
    from routes.onboarding import get_onboarding
    return await get_onboarding(str(emp.id), db, current_user)


# ── Admin: link employee to user account ────────────────────────
@router.post("/admin/link")
async def link_employee_to_user(
    user_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Admin: link a user account to an employee record for self-service access."""
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin required")

    existing = await db.execute(
        select(EmployeeUserLink).where(EmployeeUserLink.user_id == user_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "User already linked to an employee")

    link = EmployeeUserLink(user_id=user_id, employee_id=employee_id)
    db.add(link)
    await db.commit()
    return {"message": "Employee linked to user account", "user_id": user_id, "employee_id": employee_id}


@router.get("/admin/links")
async def list_employee_links(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Admin: list all employee-user links."""
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin required")
    result = await db.execute(select(EmployeeUserLink))
    links = result.scalars().all()
    return [{"user_id": str(l.user_id), "employee_id": str(l.employee_id)} for l in links]
