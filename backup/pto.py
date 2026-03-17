"""
PTO (Paid Time Off) tracking system.
Tracks accrual, requests, approvals, and balances per employee.

Tables: pto_policies, pto_balances, pto_requests
"""
import uuid
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Numeric, Integer, Boolean, Date, DateTime, ForeignKey, Text, select, func
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/pto", tags=["pto"])


# ── Models ─────────────────────────────────────────────────────
class PtoPolicy(Base):
    __tablename__ = "pto_policies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)         # "Standard PTO", "Executive", etc.
    accrual_rate = Column(Numeric(8, 4), default=0)    # hours per pay period
    max_accrual = Column(Numeric(8, 2), default=240)   # max hours (0 = unlimited)
    carryover_limit = Column(Numeric(8, 2), default=80) # hours carried to next year
    waiting_period_days = Column(Integer, default=90)  # days before eligible
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PtoBalance(Base):
    __tablename__ = "pto_balances"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    policy_id = Column(UUID(as_uuid=True), ForeignKey("pto_policies.id"), nullable=True)
    available_hours = Column(Numeric(8, 2), default=0)
    used_hours = Column(Numeric(8, 2), default=0)
    pending_hours = Column(Numeric(8, 2), default=0)
    ytd_accrued = Column(Numeric(8, 2), default=0)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PtoRequest(Base):
    __tablename__ = "pto_requests"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    hours = Column(Numeric(8, 2), nullable=False)
    pto_type = Column(String(30), default="pto")   # pto | sick | personal | bereavement
    status = Column(String(20), default="pending") # pending | approved | denied | cancelled
    notes = Column(Text)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Schemas ────────────────────────────────────────────────────
class PolicyCreate(BaseModel):
    name: str
    accrual_rate: float = 3.08     # ~80hrs/yr on biweekly
    max_accrual: float = 240
    carryover_limit: float = 80
    waiting_period_days: int = 90


class RequestCreate(BaseModel):
    employee_id: str
    start_date: date
    end_date: date
    hours: float
    pto_type: str = "pto"
    notes: Optional[str] = None


class RequestReview(BaseModel):
    status: str   # approved | denied
    notes: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────
@router.get("/policies")
async def list_policies(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PtoPolicy).where(PtoPolicy.company_id == current_user["company_id"])
    )
    return [_ser_policy(p) for p in result.scalars().all()]


@router.post("/policies", status_code=201)
async def create_policy(
    body: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    policy = PtoPolicy(company_id=current_user["company_id"], **body.model_dump())
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return _ser_policy(policy)


@router.get("/balances")
async def list_balances(
    employee_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(PtoBalance).where(PtoBalance.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(PtoBalance.employee_id == employee_id)
    result = await db.execute(q)
    return [_ser_balance(b) for b in result.scalars().all()]


@router.post("/balances/adjust")
async def adjust_balance(
    employee_id: str,
    hours: float,
    reason: str = "manual adjustment",
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually add or subtract PTO hours (admin only)."""
    result = await db.execute(
        select(PtoBalance).where(
            PtoBalance.employee_id == employee_id,
            PtoBalance.company_id == current_user["company_id"],
        )
    )
    bal = result.scalar_one_or_none()
    if not bal:
        # Create balance record if missing
        bal = PtoBalance(
            employee_id=employee_id,
            company_id=current_user["company_id"],
            available_hours=0,
        )
        db.add(bal)

    bal.available_hours = float(bal.available_hours or 0) + hours
    bal.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(bal)
    return _ser_balance(bal)


@router.post("/balances/accrue")
async def run_accrual(
    pay_period_end: date,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Run PTO accrual for all employees on a pay period.
    Called automatically after each payroll run, or manually here.
    """
    from models import Employee
    emp_result = await db.execute(
        select(Employee).where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
    )
    employees = emp_result.scalars().all()

    # Get default policy
    pol_result = await db.execute(
        select(PtoPolicy).where(
            PtoPolicy.company_id == current_user["company_id"],
            PtoPolicy.is_active == True,
        ).limit(1)
    )
    policy = pol_result.scalar_one_or_none()
    if not policy:
        return {"message": "No active PTO policy found", "accrued": 0}

    accrued_count = 0
    for emp in employees:
        # Check waiting period
        days_employed = (pay_period_end - emp.hire_date).days if emp.hire_date else 0
        if days_employed < policy.waiting_period_days:
            continue

        # Get or create balance
        bal_result = await db.execute(
            select(PtoBalance).where(PtoBalance.employee_id == emp.id)
        )
        bal = bal_result.scalar_one_or_none()
        if not bal:
            bal = PtoBalance(
                employee_id=emp.id,
                company_id=emp.company_id,
                policy_id=policy.id,
                available_hours=0,
            )
            db.add(bal)

        current = float(bal.available_hours or 0)
        rate = float(policy.accrual_rate)
        max_acc = float(policy.max_accrual)

        new_total = current + rate
        if max_acc > 0:
            new_total = min(new_total, max_acc)

        bal.available_hours = new_total
        bal.ytd_accrued = float(bal.ytd_accrued or 0) + rate
        bal.updated_at = datetime.utcnow()
        accrued_count += 1

    await db.commit()
    return {
        "accrued_for": accrued_count,
        "hours_per_employee": float(policy.accrual_rate),
        "policy": policy.name,
    }


@router.get("/requests")
async def list_requests(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(PtoRequest).where(PtoRequest.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(PtoRequest.employee_id == employee_id)
    if status:
        q = q.where(PtoRequest.status == status)
    q = q.order_by(PtoRequest.created_at.desc()).limit(200)
    result = await db.execute(q)
    return [_ser_request(r) for r in result.scalars().all()]


@router.post("/requests", status_code=201)
async def create_request(
    body: RequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Check balance
    bal_result = await db.execute(
        select(PtoBalance).where(PtoBalance.employee_id == body.employee_id)
    )
    bal = bal_result.scalar_one_or_none()
    if bal and float(bal.available_hours or 0) < body.hours:
        raise HTTPException(400, f"Insufficient PTO balance. Available: {bal.available_hours}h, Requested: {body.hours}h")

    req = PtoRequest(
        company_id=current_user["company_id"],
        **body.model_dump(),
    )
    db.add(req)

    # Mark hours as pending
    if bal:
        bal.pending_hours = float(bal.pending_hours or 0) + body.hours

    await db.commit()
    await db.refresh(req)
    return _ser_request(req)


@router.put("/requests/{req_id}/review")
async def review_request(
    req_id: str,
    body: RequestReview,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PtoRequest).where(
            PtoRequest.id == req_id,
            PtoRequest.company_id == current_user["company_id"],
        )
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(404, "PTO request not found")
    if req.status != "pending":
        raise HTTPException(400, f"Request already {req.status}")

    req.status = body.status
    req.reviewed_by = current_user["sub"]
    req.reviewed_at = datetime.utcnow()
    if body.notes:
        req.notes = (req.notes or "") + f"\nReview note: {body.notes}"

    # Update balance
    bal_result = await db.execute(
        select(PtoBalance).where(PtoBalance.employee_id == req.employee_id)
    )
    bal = bal_result.scalar_one_or_none()
    if bal:
        bal.pending_hours = max(0, float(bal.pending_hours or 0) - float(req.hours))
        if body.status == "approved":
            bal.available_hours = max(0, float(bal.available_hours or 0) - float(req.hours))
            bal.used_hours = float(bal.used_hours or 0) + float(req.hours)

    await db.commit()
    await db.refresh(req)
    return _ser_request(req)


def _ser_policy(p: PtoPolicy) -> dict:
    return {
        "id": str(p.id), "name": p.name,
        "accrual_rate": float(p.accrual_rate),
        "max_accrual": float(p.max_accrual),
        "carryover_limit": float(p.carryover_limit),
        "waiting_period_days": p.waiting_period_days,
        "is_active": p.is_active,
    }

def _ser_balance(b: PtoBalance) -> dict:
    avail = float(b.available_hours or 0)
    used = float(b.used_hours or 0)
    pending = float(b.pending_hours or 0)
    return {
        "id": str(b.id),
        "employee_id": str(b.employee_id),
        "available_hours": avail,
        "used_hours": used,
        "pending_hours": pending,
        "net_available": avail - pending,
        "ytd_accrued": float(b.ytd_accrued or 0),
        "updated_at": str(b.updated_at),
    }

def _ser_request(r: PtoRequest) -> dict:
    return {
        "id": str(r.id),
        "employee_id": str(r.employee_id),
        "start_date": str(r.start_date),
        "end_date": str(r.end_date),
        "hours": float(r.hours),
        "pto_type": r.pto_type,
        "status": r.status,
        "notes": r.notes,
        "created_at": str(r.created_at),
        "reviewed_at": str(r.reviewed_at) if r.reviewed_at else None,
    }
