"""
Expense reimbursement system.
Employees submit expense reports; managers approve; reimbursed via payroll.

POST   /expenses              submit expense
GET    /expenses              list (filter by employee, status, date range)
PUT    /expenses/{id}/approve
PUT    /expenses/{id}/deny
GET    /expenses/pending-payroll  approved expenses not yet included in a payroll run
POST   /expenses/batch-reimburse  mark a list of expenses as reimbursed (after payroll run)
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (Column, String, Numeric, Boolean, Date,
                        DateTime, ForeignKey, Text, select, func)
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/expenses", tags=["expenses"])

EXPENSE_CATEGORIES = [
    "travel", "meals", "accommodation", "supplies", "software",
    "equipment", "training", "marketing", "other",
]


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    expense_date = Column(Date, nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    vendor = Column(String(200))
    receipt_url = Column(Text)               # path to uploaded receipt
    status = Column(String(20), default="pending")  # pending|approved|denied|reimbursed
    is_billable = Column(Boolean, default=False)  # billable to a client
    project_code = Column(String(50))
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True))
    denied_reason = Column(Text)
    reimbursed_at = Column(DateTime(timezone=True))
    pay_run_id = Column(UUID(as_uuid=True), ForeignKey("pay_runs.id"), nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ExpenseCreate(BaseModel):
    expense_date: date
    category: str
    description: str
    amount: float
    currency: str = "USD"
    vendor: Optional[str] = None
    is_billable: bool = False
    project_code: Optional[str] = None
    notes: Optional[str] = None


class ExpenseReview(BaseModel):
    denied_reason: Optional[str] = None


@router.get("")
async def list_expenses(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(Expense).where(Expense.company_id == current_user["company_id"])
    if employee_id: q = q.where(Expense.employee_id == employee_id)
    if status:      q = q.where(Expense.status == status)
    if category:    q = q.where(Expense.category == category)
    if start_date:  q = q.where(Expense.expense_date >= start_date)
    if end_date:    q = q.where(Expense.expense_date <= end_date)
    q = q.order_by(Expense.expense_date.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    expenses = result.scalars().all()

    total_res = await db.execute(
        select(func.sum(Expense.amount), func.count(Expense.id))
        .where(Expense.company_id == current_user["company_id"],
               Expense.status == "approved")
    )
    total_row = total_res.first()

    return {
        "expenses": [_ser(e) for e in expenses],
        "pending_reimbursement": float(total_row[0] or 0),
        "approved_count": total_row[1] or 0,
    }


@router.post("", status_code=201)
async def submit_expense(
    employee_id: str,
    body: ExpenseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.category not in EXPENSE_CATEGORIES:
        raise HTTPException(400, f"Category must be: {', '.join(EXPENSE_CATEGORIES)}")
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be positive")

    expense = Expense(
        company_id=current_user["company_id"],
        employee_id=employee_id,
        **body.model_dump(),
    )
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return _ser(expense)


@router.put("/{expense_id}/approve")
async def approve_expense(
    expense_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    expense = await _get_or_404(db, expense_id, current_user["company_id"])
    if expense.status != "pending":
        raise HTTPException(400, f"Expense is already {expense.status}")
    expense.status = "approved"
    expense.approved_by = current_user["sub"]
    expense.approved_at = datetime.utcnow()
    await db.commit()
    return _ser(expense)


@router.put("/{expense_id}/deny")
async def deny_expense(
    expense_id: str,
    body: ExpenseReview,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    expense = await _get_or_404(db, expense_id, current_user["company_id"])
    if expense.status != "pending":
        raise HTTPException(400, f"Expense is already {expense.status}")
    expense.status = "denied"
    expense.denied_reason = body.denied_reason
    expense.approved_by = current_user["sub"]
    expense.approved_at = datetime.utcnow()
    await db.commit()
    return _ser(expense)


@router.get("/pending-payroll")
async def pending_payroll_reimbursements(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Approved expenses not yet reimbursed — include in next payroll run."""
    result = await db.execute(
        select(Expense).where(
            Expense.company_id == current_user["company_id"],
            Expense.status == "approved",
            Expense.reimbursed_at == None,
        ).order_by(Expense.employee_id, Expense.expense_date)
    )
    expenses = result.scalars().all()

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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark expenses as reimbursed after payroll run."""
    now = datetime.utcnow()
    reimbursed = 0
    total = 0.0
    for eid in expense_ids:
        result = await db.execute(
            select(Expense).where(
                Expense.id == eid,
                Expense.company_id == current_user["company_id"],
                Expense.status == "approved",
            )
        )
        expense = result.scalar_one_or_none()
        if expense:
            expense.status = "reimbursed"
            expense.reimbursed_at = now
            if pay_run_id:
                expense.pay_run_id = pay_run_id
            reimbursed += 1
            total += float(expense.amount)
    await db.commit()
    return {"reimbursed": reimbursed, "total_amount": round(total, 2)}


@router.get("/categories")
async def list_categories():
    return EXPENSE_CATEGORIES


@router.get("/report")
async def expense_report(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Annual expense report by category."""
    year = year or date.today().year
    result = await db.execute(
        select(
            Expense.category,
            func.count(Expense.id).label("count"),
            func.sum(Expense.amount).label("total"),
        )
        .where(
            Expense.company_id == current_user["company_id"],
            func.extract("year", Expense.expense_date) == year,
            Expense.status.in_(["approved", "reimbursed"]),
        )
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
    )
    rows = result.all()
    grand_total = sum(float(r.total or 0) for r in rows)
    return {
        "year": year,
        "grand_total": round(grand_total, 2),
        "by_category": [
            {
                "category": r.category,
                "count": r.count,
                "total": round(float(r.total or 0), 2),
                "pct": round(float(r.total or 0) / grand_total * 100, 1) if grand_total else 0,
            }
            for r in rows
        ],
    }


async def _get_or_404(db, expense_id, company_id):
    result = await db.execute(
        select(Expense).where(Expense.id == expense_id, Expense.company_id == company_id)
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(404, "Expense not found")
    return exp


def _ser(e: Expense) -> dict:
    return {
        "id": str(e.id), "employee_id": str(e.employee_id),
        "expense_date": str(e.expense_date), "category": e.category,
        "description": e.description, "amount": float(e.amount),
        "currency": e.currency, "vendor": e.vendor,
        "status": e.status, "is_billable": e.is_billable,
        "project_code": e.project_code,
        "denied_reason": e.denied_reason,
        "approved_at": str(e.approved_at) if e.approved_at else None,
        "reimbursed_at": str(e.reimbursed_at) if e.reimbursed_at else None,
        "created_at": str(e.created_at),
    }
