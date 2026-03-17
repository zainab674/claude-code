"""
Garnishment order management.
Supports: child support, federal tax levy, student loan, creditor, bankruptcy.

Each employee can have multiple active garnishment orders.
"""
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import GarnishmentOrder, Employee
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/garnishments", tags=["garnishments"])

GARNISHMENT_TYPES = {
    "child_support":    {"priority": 1, "max_pct": 0.50, "label": "Child Support"},
    "federal_tax_levy": {"priority": 2, "max_pct": 0.15, "label": "Federal Tax Levy"},
    "student_loan":     {"priority": 3, "max_pct": 0.15, "label": "Student Loan"},
    "creditor":         {"priority": 4, "max_pct": 0.25, "label": "Creditor Garnishment"},
    "bankruptcy":       {"priority": 5, "max_pct": 0.10, "label": "Bankruptcy"},
    "state_tax_levy":   {"priority": 6, "max_pct": 0.10, "label": "State Tax Levy"},
}


# ── Schemas ────────────────────────────────────────────────────
class GarnishmentCreate(BaseModel):
    employee_id: str
    garnishment_type: str   # child_support|tax_levy|student_loan|creditor
    case_number: Optional[str] = None
    issuing_agency: Optional[str] = None
    amount_per_period: float
    amount_type: str = "fixed"   # fixed|percentage
    percentage: Optional[float] = None
    max_total: float = 0
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────
@router.get("")
async def list_garnishments(
    employee_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = UUID(employee_id)
    
    orders = await GarnishmentOrder.find(query).sort("-created_at").to_list()
    out = []
    for o in orders:
        emp = await Employee.find_one(Employee.id == o.employee_id)
        out.append({
            **_serialize(o),
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
        })
    return out


@router.post("", status_code=201)
async def create_garnishment(
    body: GarnishmentCreate,
    current_user: dict = Depends(get_current_user),
):
    if body.garnishment_type not in GARNISHMENT_TYPES:
        raise HTTPException(400, f"Invalid type. Must be: {', '.join(GARNISHMENT_TYPES)}")

    order = GarnishmentOrder(
        company_id=current_user["company_id"],
        employee_id=UUID(body.employee_id),
        garnishment_type=body.garnishment_type,
        case_number=body.case_number,
        issuing_agency=body.issuing_agency,
        amount_per_period=body.amount_per_period,
        amount_type=body.amount_type,
        percentage=body.percentage,
        max_total=body.max_total,
        start_date=datetime.combine(body.start_date, datetime.min.time()),
        end_date=datetime.combine(body.end_date, datetime.min.time()) if body.end_date else None,
        notes=body.notes
    )
    await order.insert()
    await _sync_employee_garnishment(order.employee_id, order.company_id)
    return _serialize(order)


@router.put("/{order_id}/deactivate", status_code=200)
async def deactivate_order(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    order = await GarnishmentOrder.find_one(
        GarnishmentOrder.id == UUID(order_id),
        GarnishmentOrder.company_id == current_user["company_id"],
    )
    if not order:
        raise HTTPException(404, "Order not found")
        
    order.is_active = False
    order.end_date = datetime.now()
    await order.save()
    await _sync_employee_garnishment(order.employee_id, order.company_id)
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
    current_user: dict = Depends(get_current_user),
):
    orders = await GarnishmentOrder.find(
        GarnishmentOrder.employee_id == UUID(employee_id),
        GarnishmentOrder.company_id == current_user["company_id"],
        GarnishmentOrder.is_active == True,
    ).to_list()
    
    if not orders:
        return {"total": 0.0, "orders": [], "disposable_income": net_disposable_income}

    # CCPA: max 25% of disposable income for most garnishments
    ccpa_max = net_disposable_income * 0.25
    remaining = net_disposable_income
    results = []

    for order in sorted(orders, key=lambda o: GARNISHMENT_TYPES.get(o.garnishment_type, {}).get("priority", 9)):
        if remaining <= 0:
            results.append({"order_id": str(order.id), "type": order.garnishment_type, "amount": 0.0, "reason": "no disposable income remaining"})
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
            calculated = max(0.0, float(order.max_total) - float(order.total_paid))

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


async def _sync_employee_garnishment(employee_id: UUID, company_id: UUID):
    """Update employee.garnishment_amount to sum of all active fixed orders."""
    active = await GarnishmentOrder.find(
        GarnishmentOrder.employee_id == employee_id,
        GarnishmentOrder.company_id == company_id,
        GarnishmentOrder.is_active == True,
        GarnishmentOrder.amount_type == "fixed",
    ).to_list()
    
    total = sum(float(o.amount_per_period) for o in active)

    emp = await Employee.find_one(Employee.id == employee_id)
    if emp:
        emp.garnishment_amount = total
        await emp.save()


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
        "start_date": str(o.start_date.date()) if isinstance(o.start_date, datetime) else str(o.start_date),
        "end_date": str(o.end_date.date()) if isinstance(o.end_date, datetime) else (str(o.end_date) if o.end_date else None),
        "is_active": o.is_active,
        "notes": o.notes,
        "created_at": str(o.created_at),
    }
