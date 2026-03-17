import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import PayrollAdjustment
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/adjustments", tags=["adjustments"])

ADJUSTMENT_TYPES = [
    "bonus_annual", "bonus_holiday", "bonus_spot", "bonus_signing",
    "correction_underpaid", "correction_overpaid",
    "off_cycle_termination", "off_cycle_other",
    "commission", "stipend", "reimbursement_bulk",
]


class AdjustmentCreate(BaseModel):
    employee_id: str
    adjustment_type: str
    amount: float
    is_taxable: bool = True
    description: str
    effective_date: date
    notes: Optional[str] = None


class BulkAdjustmentCreate(BaseModel):
    adjustments: List[AdjustmentCreate]


@router.get("")
async def list_adjustments(
    employee_id: Optional[str] = None,
    status: Optional[str] = "pending",
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = UUID(employee_id)
    if status:
        query["status"] = status
    
    adjustments = await PayrollAdjustment.find(query).sort("-effective_date").to_list()

    total_pending = sum(float(a.amount) for a in adjustments if a.status == "pending")
    return {
        "total_pending_amount": round(total_pending, 2),
        "adjustments": [_ser(a) for a in adjustments],
    }


@router.post("", status_code=201)
async def create_adjustment(
    body: AdjustmentCreate,
    current_user: dict = Depends(get_current_user),
):
    if body.adjustment_type not in ADJUSTMENT_TYPES:
        raise HTTPException(400, f"adjustment_type must be one of: {', '.join(ADJUSTMENT_TYPES)}")
    if body.amount == 0:
        raise HTTPException(400, "Amount cannot be zero")

    adj = PayrollAdjustment(
        company_id=current_user["company_id"],
        created_by=current_user["sub"],
        employee_id=UUID(body.employee_id),
        adjustment_type=body.adjustment_type,
        amount=body.amount,
        is_taxable=body.is_taxable,
        description=body.description,
        effective_date=body.effective_date,
        notes=body.notes,
        status="pending",
    )
    await adj.insert()
    return _ser(adj)


@router.post("/bulk", status_code=201)
async def create_bulk_adjustments(
    body: BulkAdjustmentCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create multiple adjustments at once."""
    if len(body.adjustments) > 500:
        raise HTTPException(400, "Maximum 500 adjustments per bulk request")

    company_id = current_user["company_id"]
    created_by = current_user["sub"]
    
    adjs_to_create = []
    total = 0.0
    for item in body.adjustments:
        if item.adjustment_type not in ADJUSTMENT_TYPES:
            continue
        adj = PayrollAdjustment(
            company_id=company_id,
            created_by=created_by,
            employee_id=UUID(item.employee_id),
            adjustment_type=item.adjustment_type,
            amount=item.amount,
            is_taxable=item.is_taxable,
            description=item.description,
            effective_date=item.effective_date,
            notes=item.notes,
            status="pending",
        )
        adjs_to_create.append(adj)
        total += item.amount

    if adjs_to_create:
        await PayrollAdjustment.insert_many(adjs_to_create)

    return {
        "created": len(adjs_to_create),
        "total_amount": round(total, 2),
        "message": f"Created {len(adjs_to_create)} adjustments totaling ${total:,.2f}",
    }


@router.post("/apply")
async def apply_adjustments(
    adjustment_ids: List[str],
    pay_run_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark adjustments as applied to a specific pay run."""
    company_id = current_user["company_id"]
    pay_run_uuid = UUID(pay_run_id)
    user_id = current_user["sub"]
    now = datetime.utcnow()
    
    applied = 0
    for aid in adjustment_ids:
        adj = await PayrollAdjustment.find_one(
            PayrollAdjustment.id == UUID(aid),
            PayrollAdjustment.company_id == company_id,
            PayrollAdjustment.status == "pending",
        )
        if adj:
            adj.status = "applied"
            adj.pay_run_id = pay_run_uuid
            adj.applied_at = now
            adj.approved_by = user_id
            await adj.save()
            applied += 1
    
    return {"applied": applied, "pay_run_id": pay_run_id}


@router.delete("/{adj_id}", status_code=204)
async def cancel_adjustment(
    adj_id: str,
    current_user: dict = Depends(get_current_user),
):
    adj = await PayrollAdjustment.find_one(
        PayrollAdjustment.id == UUID(adj_id),
        PayrollAdjustment.company_id == current_user["company_id"],
    )
    if not adj:
        raise HTTPException(404, "Adjustment not found")
    if adj.status == "applied":
        raise HTTPException(400, "Cannot cancel an applied adjustment")
    
    adj.status = "cancelled"
    await adj.save()


@router.get("/types")
async def list_adjustment_types():
    return [{"key": t, "label": t.replace("_", " ").title()} for t in ADJUSTMENT_TYPES]


def _ser(a: PayrollAdjustment) -> dict:
    return {
        "id": str(a.id), "employee_id": str(a.employee_id),
        "adjustment_type": a.adjustment_type,
        "amount": float(a.amount), "is_taxable": a.is_taxable,
        "description": a.description,
        "effective_date": str(a.effective_date),
        "status": a.status,
        "pay_run_id": str(a.pay_run_id) if a.pay_run_id else None,
        "notes": a.notes, "created_at": str(a.created_at),
        "applied_at": str(a.applied_at) if a.applied_at else None,
    }
