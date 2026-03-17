"""
Bulk payroll adjustments.
Create off-cycle payments and bulk adjustments outside of regular payroll runs.

Use cases:
  - One-time bonuses (annual, holiday, spot bonus)
  - Pay corrections (missed paycheck, wrong amount)
  - Off-cycle termination pay
  - Sign-on bonuses

POST /adjustments              create adjustment(s)
GET  /adjustments              list pending adjustments
POST /adjustments/apply        apply to a pay run
DELETE /adjustments/{id}       cancel adjustment
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (Column, String, Numeric, Boolean, Date,
                        DateTime, ForeignKey, Text, select, func)
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/adjustments", tags=["adjustments"])

ADJUSTMENT_TYPES = [
    "bonus_annual", "bonus_holiday", "bonus_spot", "bonus_signing",
    "correction_underpaid", "correction_overpaid",
    "off_cycle_termination", "off_cycle_other",
    "commission", "stipend", "reimbursement_bulk",
]


class PayrollAdjustment(Base):
    __tablename__ = "payroll_adjustments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    adjustment_type = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    is_taxable = Column(Boolean, default=True)
    description = Column(Text)
    effective_date = Column(Date, nullable=False)
    status = Column(String(20), default="pending")  # pending|applied|cancelled
    pay_run_id = Column(UUID(as_uuid=True), ForeignKey("pay_runs.id"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    applied_at = Column(DateTime(timezone=True))


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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(PayrollAdjustment).where(
        PayrollAdjustment.company_id == current_user["company_id"]
    )
    if employee_id: q = q.where(PayrollAdjustment.employee_id == employee_id)
    if status:      q = q.where(PayrollAdjustment.status == status)
    q = q.order_by(PayrollAdjustment.effective_date.desc())
    result = await db.execute(q)
    adjustments = result.scalars().all()

    total_pending = sum(float(a.amount) for a in adjustments if a.status == "pending")
    return {
        "total_pending_amount": round(total_pending, 2),
        "adjustments": [_ser(a) for a in adjustments],
    }


@router.post("", status_code=201)
async def create_adjustment(
    body: AdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.adjustment_type not in ADJUSTMENT_TYPES:
        raise HTTPException(400, f"adjustment_type must be one of: {', '.join(ADJUSTMENT_TYPES)}")
    if body.amount == 0:
        raise HTTPException(400, "Amount cannot be zero")

    adj = PayrollAdjustment(
        company_id=current_user["company_id"],
        created_by=current_user["sub"],
        **body.model_dump(),
    )
    db.add(adj)
    await db.commit()
    await db.refresh(adj)
    return _ser(adj)


@router.post("/bulk", status_code=201)
async def create_bulk_adjustments(
    body: BulkAdjustmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create multiple adjustments at once (e.g., annual bonus for all employees)."""
    if len(body.adjustments) > 500:
        raise HTTPException(400, "Maximum 500 adjustments per bulk request")

    created = []
    total = 0.0
    for item in body.adjustments:
        if item.adjustment_type not in ADJUSTMENT_TYPES:
            continue
        adj = PayrollAdjustment(
            company_id=current_user["company_id"],
            created_by=current_user["sub"],
            **item.model_dump(),
        )
        db.add(adj)
        created.append(adj)
        total += item.amount

    await db.commit()
    return {
        "created": len(created),
        "total_amount": round(total, 2),
        "message": f"Created {len(created)} adjustments totaling ${total:,.2f}",
    }


@router.post("/apply")
async def apply_adjustments(
    adjustment_ids: List[str],
    pay_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark adjustments as applied to a specific pay run."""
    now = datetime.utcnow()
    applied = 0
    for aid in adjustment_ids:
        result = await db.execute(
            select(PayrollAdjustment).where(
                PayrollAdjustment.id == aid,
                PayrollAdjustment.company_id == current_user["company_id"],
                PayrollAdjustment.status == "pending",
            )
        )
        adj = result.scalar_one_or_none()
        if adj:
            adj.status = "applied"
            adj.pay_run_id = pay_run_id
            adj.applied_at = now
            adj.approved_by = current_user["sub"]
            applied += 1
    await db.commit()
    return {"applied": applied, "pay_run_id": pay_run_id}


@router.delete("/{adj_id}", status_code=204)
async def cancel_adjustment(
    adj_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PayrollAdjustment).where(
            PayrollAdjustment.id == adj_id,
            PayrollAdjustment.company_id == current_user["company_id"],
        )
    )
    adj = result.scalar_one_or_none()
    if not adj:
        raise HTTPException(404, "Adjustment not found")
    if adj.status == "applied":
        raise HTTPException(400, "Cannot cancel an applied adjustment")
    adj.status = "cancelled"
    await db.commit()


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
