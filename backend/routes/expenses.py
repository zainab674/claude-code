"""
Expense reimbursement system.
Employees submit expense reports; managers approve; reimbursed via payroll.
"""
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import Expense, Employee
from utils.auth import get_current_user
from uuid import UUID
from utils.numbers import to_float

router = APIRouter(prefix="/expenses", tags=["expenses"])

EXPENSE_CATEGORIES = {
    "travel", "meals", "office_supplies", "software", "home_office", "other"
}

# ── Schemas ────────────────────────────────────────────────────
class ExpenseCreate(BaseModel):
    employee_id: str
    expense_date: date
    category: str
    description: str
    amount: float
    currency: str = "USD"
    vendor: Optional[str] = None
    receipt_url: Optional[str] = None
    is_billable: bool = False
    project_code: Optional[str] = None


class ExpenseReview(BaseModel):
    status: str   # approved|denied
    denied_reason: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────
@router.get("")
async def list_expenses(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]
    query = {"company_id": company_id}
    if employee_id: query["employee_id"] = UUID(employee_id)
    if status:      query["status"] = status
    if category:    query["category"] = category
    if start_date:  query["expense_date"] = {"$gte": datetime.combine(start_date, datetime.min.time())}
    if end_date:    
        if "$gte" in query.get("expense_date", {}):
            query["expense_date"]["$lte"] = datetime.combine(end_date, datetime.max.time())
        else:
            query["expense_date"] = {"$lte": datetime.combine(end_date, datetime.max.time())}
    
    expenses = await Expense.find(query).sort("-expense_date").skip(skip).limit(limit).to_list()

    # Get summary stats via aggregation
    pipeline = [
        {"$match": {"company_id": company_id, "status": "approved", "reimbursed_at": None}},
        {"$group": {"_id": None, "total_amount": {"$sum": "$amount"}, "count": {"$sum": 1}}}
    ]
    summary = await Expense.aggregate(pipeline).to_list()
    total_row = summary[0] if summary else {"total_amount": 0, "count": 0}

    return {
        "expenses": [_ser(e) for e in expenses],
        "pending_reimbursement": to_float(total_row["total_amount"]),
        "approved_count": total_row["count"],
    }


@router.post("", status_code=201)
async def submit_expense(
    body: ExpenseCreate,
    current_user: dict = Depends(get_current_user),
):
    if body.category not in EXPENSE_CATEGORIES:
        raise HTTPException(400, f"Category must be: {', '.join(EXPENSE_CATEGORIES)}")
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    expense = Expense(
        company_id=current_user["company_id"],
        employee_id=UUID(body.employee_id),
        expense_date=datetime.combine(body.expense_date, datetime.min.time()),
        category=body.category,
        description=body.description,
        amount=body.amount,
        currency=body.currency,
        vendor=body.vendor,
        receipt_url=body.receipt_url,
        is_billable=body.is_billable,
        project_code=body.project_code,
        status="pending"
    )
    await expense.insert()
    return _ser(expense)


@router.put("/{expense_id}/approve")
async def approve_expense(
    expense_id: str,
    current_user: dict = Depends(get_current_user),
):
    expense = await _get_or_404(expense_id, current_user["company_id"])
    if expense.status != "pending":
        raise HTTPException(400, f"Expense is already {expense.status}")
    expense.status = "approved"
    expense.approved_by = current_user["sub"]
    expense.approved_at = datetime.utcnow()
    await expense.save()
    return _ser(expense)


@router.put("/{expense_id}/deny")
async def deny_expense(
    expense_id: str,
    body: ExpenseReview,
    current_user: dict = Depends(get_current_user),
):
    expense = await _get_or_404(expense_id, current_user["company_id"])
    if expense.status != "pending":
        raise HTTPException(400, f"Expense is already {expense.status}")
    expense.status = "denied"
    expense.denied_reason = body.denied_reason
    expense.approved_by = current_user["sub"]
    expense.approved_at = datetime.utcnow()
    await expense.save()
    return _ser(expense)


@router.get("/pending-payroll")
async def pending_payroll_reimbursements(
    current_user: dict = Depends(get_current_user),
):
    """Approved expenses not yet reimbursed — include in next payroll run."""
    expenses = await Expense.find(
        Expense.company_id == current_user["company_id"],
        Expense.status == "approved",
        Expense.reimbursed_at == None,
    ).sort(Expense.employee_id, Expense.expense_date).to_list()

    # Group by employee
    by_employee: dict = {}
    for e in expenses:
        eid = str(e.employee_id)
        if eid not in by_employee:
            by_employee[eid] = {"employee_id": eid, "total": 0.0, "expenses": []}
        by_employee[eid]["total"] += float(e.amount)
        by_employee[eid]["expenses"].append(_ser(e))

    return {
        "total_employees": len(by_employee),
        "total_amount": round(sum(v["total"] for v in by_employee.values()), 2),
        "by_employee": list(by_employee.values()),
    }


@router.post("/batch-reimburse")
async def batch_reimburse(
    expense_ids: List[str],
    pay_run_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Mark expenses as reimbursed after payroll run."""
    now = datetime.utcnow()
    reimbursed = 0
    total = 0.0
    company_id = current_user["company_id"]
    
    for eid in expense_ids:
        expense = await Expense.find_one(
            Expense.id == UUID(eid),
            Expense.company_id == company_id,
            Expense.status == "approved",
        )
        if expense:
            expense.status = "reimbursed"
            expense.reimbursed_at = now
            if pay_run_id:
                expense.pay_run_id = UUID(pay_run_id)
            await expense.save()
            reimbursed += 1
            total += float(expense.amount)
            
    return {"reimbursed": reimbursed, "total_amount": round(total, 2)}


@router.get("/categories")
async def list_categories():
    return list(EXPENSE_CATEGORIES)


@router.get("/report")
async def expense_report(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Annual expense report by category."""
    year = year or date.today().year
    company_id = current_user["company_id"]
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)
    
    pipeline = [
        {
            "$match": {
                "company_id": company_id,
                "expense_date": {"$gte": year_start, "$lte": year_end},
                "status": {"$in": ["approved", "reimbursed"]}
            }
        },
        {
            "$group": {
                "_id": "$category",
                "count": {"$sum": 1},
                "total": {"$sum": "$amount"}
            }
        },
        {"$sort": {"total": -1}}
    ]
    
    rows = await Expense.aggregate(pipeline).to_list()
    grand_total = sum(to_float(r["total"]) for r in rows)
    
    return {
        "year": year,
        "grand_total": round(grand_total, 2),
        "by_category": [
            {
                "category": r["_id"],
                "count": r["count"],
                "total": round(to_float(r["total"]), 2),
                "pct": round(to_float(r["total"]) / grand_total * 100, 1) if grand_total else 0,
            }
            for r in rows
        ],
    }


async def _get_or_404(expense_id: str, company_id: UUID):
    exp = await Expense.find_one(Expense.id == UUID(expense_id), Expense.company_id == company_id)
    if not exp:
        raise HTTPException(404, "Expense not found")
    return exp


def _ser(e: Expense) -> dict:
    return {
        "id": str(e.id), "employee_id": str(e.employee_id),
        "expense_date": str(e.expense_date.date()) if isinstance(e.expense_date, datetime) else str(e.expense_date),
        "category": e.category,
        "description": e.description, "amount": float(e.amount),
        "currency": e.currency, "vendor": e.vendor,
        "status": e.status, "is_billable": e.is_billable,
        "project_code": e.project_code,
        "denied_reason": e.denied_reason,
        "approved_at": str(e.approved_at) if e.approved_at else None,
        "reimbursed_at": str(e.reimbursed_at) if e.reimbursed_at else None,
        "created_at": str(e.created_at),
    }
