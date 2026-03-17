"""
PTO (Paid Time Off) tracking system.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import Employee, PtoPolicy, PtoBalance, PtoRequest
from utils.auth import get_current_user

router = APIRouter(prefix="/pto", tags=["pto"])


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
    current_user: dict = Depends(get_current_user),
):
    policies = await PtoPolicy.find(
        PtoPolicy.company_id == current_user["company_id"]
    ).to_list()
    return [_ser_policy(p) for p in policies]


@router.post("/policies", status_code=201)
async def create_policy(
    body: PolicyCreate,
    current_user: dict = Depends(get_current_user),
):
    policy = PtoPolicy(
        company_id=current_user["company_id"], 
        **body.model_dump()
    )
    await policy.insert()
    return _ser_policy(policy)


@router.get("/balances")
async def list_balances(
    employee_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = uuid.UUID(employee_id)
    
    balances = await PtoBalance.find(query).to_list()
    return [_ser_balance(b) for b in balances]


@router.post("/balances/adjust")
async def adjust_balance(
    employee_id: str,
    hours: float,
    reason: str = "manual adjustment",
    current_user: dict = Depends(get_current_user),
):
    """Manually add or subtract PTO hours (admin only)."""
    bal = await PtoBalance.find_one(
        PtoBalance.employee_id == uuid.UUID(employee_id),
        PtoBalance.company_id == current_user["company_id"]
    )
    if not bal:
        # Create balance record if missing
        bal = PtoBalance(
            employee_id=uuid.UUID(employee_id),
            company_id=current_user["company_id"],
            available_hours=0,
        )
        await bal.insert()

    bal.available_hours = float(bal.available_hours or 0) + hours
    bal.updated_at = datetime.utcnow()
    await bal.save()
    return _ser_balance(bal)


@router.post("/balances/accrue")
async def run_accrual(
    pay_period_end: date,
    current_user: dict = Depends(get_current_user),
):
    """
    Run PTO accrual for all employees on a pay period.
    """
    company_id = current_user["company_id"]
    employees = await Employee.find(
        Employee.company_id == company_id,
        Employee.status == "active"
    ).to_list()

    # Get default policy
    policy = await PtoPolicy.find_one(
        PtoPolicy.company_id == company_id,
        PtoPolicy.is_active == True
    )
    if not policy:
        return {"message": "No active PTO policy found", "accrued": 0}

    accrued_count = 0
    for emp in employees:
        # Check waiting period
        days_employed = (pay_period_end - emp.hire_date).days if emp.hire_date else 0
        if days_employed < policy.waiting_period_days:
            continue

        # Get or create balance
        bal = await PtoBalance.find_one(PtoBalance.employee_id == emp.id)
        if not bal:
            bal = PtoBalance(
                employee_id=emp.id,
                company_id=emp.company_id,
                policy_id=policy.id,
                available_hours=0,
            )
            await bal.insert()

        current = float(bal.available_hours or 0)
        rate = float(policy.accrual_rate)
        max_acc = float(policy.max_accrual)

        new_total = current + rate
        if max_acc > 0:
            new_total = min(new_total, max_acc)

        bal.available_hours = new_total
        bal.ytd_accrued = float(bal.ytd_accrued or 0) + rate
        bal.updated_at = datetime.utcnow()
        await bal.save()
        accrued_count += 1

    return {
        "accrued_for": accrued_count,
        "hours_per_employee": float(policy.accrual_rate),
        "policy": policy.name,
    }


@router.get("/requests")
async def list_requests(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = uuid.UUID(employee_id)
    if status:
        query["status"] = status
    
    requests = await PtoRequest.find(query).sort("-created_at").limit(200).to_list()
    return [_ser_request(r) for r in requests]


@router.post("/requests", status_code=201)
async def create_request(
    body: RequestCreate,
    current_user: dict = Depends(get_current_user),
):
    # Check balance
    bal = await PtoBalance.find_one(PtoBalance.employee_id == uuid.UUID(body.employee_id))
    if bal and float(bal.available_hours or 0) < body.hours:
        raise HTTPException(400, f"Insufficient PTO balance. Available: {bal.available_hours}h, Requested: {body.hours}h")

    req = PtoRequest(
        company_id=current_user["company_id"],
        employee_id=uuid.UUID(body.employee_id),
        **body.model_dump(exclude={"employee_id"}),
    )
    await req.insert()

    # Mark hours as pending
    if bal:
        bal.pending_hours = float(bal.pending_hours or 0) + body.hours
        await bal.save()

    return _ser_request(req)


@router.put("/requests/{req_id}/review")
async def review_request(
    req_id: uuid.UUID,
    body: RequestReview,
    current_user: dict = Depends(get_current_user),
):
    req = await PtoRequest.find_one(
        PtoRequest.id == req_id,
        PtoRequest.company_id == current_user["company_id"]
    )
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
    bal = await PtoBalance.find_one(PtoBalance.employee_id == req.employee_id)
    if bal:
        bal.pending_hours = max(0, float(bal.pending_hours or 0) - float(req.hours))
        if body.status == "approved":
            bal.available_hours = max(0, float(bal.available_hours or 0) - float(req.hours))
            bal.used_hours = float(bal.used_hours or 0) + float(req.hours)
        await bal.save()

    await req.save()
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
