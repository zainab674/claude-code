"""
Garnishment order management.
Supports: child support, federal tax levy, student loan, creditor, bankruptcy.

Each employee can have multiple active garnishment orders.
Garnishment amounts feed into payroll calculator automatically.
"""
import uuid
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Numeric, Boolean, Date, DateTime, ForeignKey, Text, Integer, select
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from models import Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/garnishments", tags=["garnishments"])

GARNISHMENT_TYPES = {
    "child_support":    {"priority": 1, "max_pct": 0.50, "label": "Child Support"},
    "federal_tax_levy": {"priority": 2, "max_pct": 0.15, "label": "Federal Tax Levy"},
    "student_loan":     {"priority": 3, "max_pct": 0.15, "label": "Student Loan"},
    "creditor":         {"priority": 4, "max_pct": 0.25, "label": "Creditor Garnishment"},
    "bankruptcy":       {"priority": 5, "max_pct": 0.10, "label": "Bankruptcy"},
    "state_tax_levy":   {"priority": 6, "max_pct": 0.10, "label": "State Tax Levy"},
}


class GarnishmentOrder(Base):
    __tablename__ = "garnishment_orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    garnishment_type = Column(String(50), nullable=False)
    case_number = Column(String(100))
    issuing_agency = Column(String(255))
    amount_per_period = Column(Numeric(10, 2), nullable=False)
    amount_type = Column(String(20), default="fixed")  # fixed | percentage
    percentage = Column(Numeric(5, 4))
    max_total = Column(Numeric(12, 2))            # 0 = no cap
    total_paid = Column(Numeric(12, 2), default=0)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date)                        # None = ongoing
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class OrderCreate(BaseModel):
    employee_id: str
    garnishment_type: str
    case_number: Optional[str] = None
    issuing_agency: Optional[str] = None
    amount_per_period: float
    amount_type: str = "fixed"
    percentage: Optional[float] = None
    max_total: float = 0
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None


@router.get("")
async def list_orders(
    employee_id: Optional[str] = None,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(GarnishmentOrder).where(GarnishmentOrder.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(GarnishmentOrder.employee_id == employee_id)
    if active_only:
        q = q.where(GarnishmentOrder.is_active == True)
    q = q.order_by(GarnishmentOrder.start_date.desc())
    result = await db.execute(q)
    orders = result.scalars().all()
    return [_serialize(o) for o in orders]


@router.post("", status_code=201)
async def create_order(
    body: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.garnishment_type not in GARNISHMENT_TYPES:
        raise HTTPException(400, f"Invalid type. Must be: {', '.join(GARNISHMENT_TYPES)}")

    order = GarnishmentOrder(
        company_id=current_user["company_id"],
        **body.model_dump(),
    )
    db.add(order)

    # Update employee's garnishment_amount to total of all active orders
    await _sync_employee_garnishment(db, body.employee_id, current_user["company_id"])

    await db.commit()
    await db.refresh(order)
    return _serialize(order)


@router.put("/{order_id}/deactivate", status_code=200)
async def deactivate_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(GarnishmentOrder).where(
            GarnishmentOrder.id == order_id,
            GarnishmentOrder.company_id == current_user["company_id"],
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    order.is_active = False
    order.end_date = date.today()
    await _sync_employee_garnishment(db, str(order.employee_id), current_user["company_id"])
    await db.commit()
    return {"message": "Order deactivated"}


@router.get("/types")
async def list_types():
    return [
        {"key": k, **v}
        for k, v in GARNISHMENT_TYPES.items()
    ]


@router.get("/employee/{employee_id}/calculate")
async def calculate_garnishment(
    employee_id: str,
    net_disposable_income: float,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Calculate garnishment amounts respecting priority rules and
    CCPA (Consumer Credit Protection Act) limits.
    """
    result = await db.execute(
        select(GarnishmentOrder)
        .where(
            GarnishmentOrder.employee_id == employee_id,
            GarnishmentOrder.company_id == current_user["company_id"],
            GarnishmentOrder.is_active == True,
        )
        .order_by(GarnishmentOrder.garnishment_type)
    )
    orders = result.scalars().all()
    if not orders:
        return {"total": 0.0, "orders": [], "disposable_income": net_disposable_income}

    # CCPA: max 25% of disposable income for most garnishments
    ccpa_max = net_disposable_income * 0.25
    remaining = net_disposable_income
    results = []

    for order in sorted(orders, key=lambda o: GARNISHMENT_TYPES.get(o.garnishment_type, {}).get("priority", 9)):
        if remaining <= 0:
            results.append({"order_id": str(order.id), "type": order.garnishment_type, "amount": 0, "reason": "no disposable income remaining"})
            continue

        type_info = GARNISHMENT_TYPES.get(order.garnishment_type, {})
        max_pct = type_info.get("max_pct", 0.25)
        type_max = net_disposable_income * max_pct

        if order.amount_type == "percentage" and order.percentage:
            calculated = net_disposable_income * float(order.percentage)
        else:
            calculated = float(order.amount_per_period)

        # Respect type maximum
        calculated = min(calculated, type_max)
        # Respect CCPA
        calculated = min(calculated, ccpa_max)
        # Respect remaining
        calculated = min(calculated, remaining)
        # Check if max_total reached
        if order.max_total and float(order.total_paid) + calculated > float(order.max_total):
            calculated = max(0, float(order.max_total) - float(order.total_paid))

        results.append({
            "order_id": str(order.id),
            "type": order.garnishment_type,
            "case_number": order.case_number,
            "calculated": round(calculated, 2),
            "type_max_pct": f"{max_pct * 100:.0f}%",
        })
        remaining -= calculated

    total = sum(r.get("calculated", 0) for r in results)
    return {
        "disposable_income": net_disposable_income,
        "total_garnishment": round(total, 2),
        "remaining_income": round(net_disposable_income - total, 2),
        "orders": results,
    }


async def _sync_employee_garnishment(db, employee_id, company_id):
    """Update employee.garnishment_amount to sum of all active fixed orders."""
    active_result = await db.execute(
        select(GarnishmentOrder).where(
            GarnishmentOrder.employee_id == employee_id,
            GarnishmentOrder.company_id == company_id,
            GarnishmentOrder.is_active == True,
            GarnishmentOrder.amount_type == "fixed",
        )
    )
    active = active_result.scalars().all()
    total = sum(float(o.amount_per_period) for o in active)

    emp_result = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = emp_result.scalar_one_or_none()
    if emp:
        emp.garnishment_amount = total


def _serialize(o: GarnishmentOrder) -> dict:
    return {
        "id": str(o.id),
        "employee_id": str(o.employee_id),
        "garnishment_type": o.garnishment_type,
        "type_label": GARNISHMENT_TYPES.get(o.garnishment_type, {}).get("label", o.garnishment_type),
        "case_number": o.case_number,
        "issuing_agency": o.issuing_agency,
        "amount_per_period": float(o.amount_per_period),
        "amount_type": o.amount_type,
        "percentage": float(o.percentage) if o.percentage else None,
        "max_total": float(o.max_total) if o.max_total else None,
        "total_paid": float(o.total_paid or 0),
        "start_date": str(o.start_date),
        "end_date": str(o.end_date) if o.end_date else None,
        "is_active": o.is_active,
        "notes": o.notes,
        "created_at": str(o.created_at),
    }
