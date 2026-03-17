"""
Employee onboarding checklist system.
Creates a checklist of tasks for each new hire.

Tables: onboarding_templates, onboarding_tasks
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

DEFAULT_TASKS = [
    ("HR Documents",        "Complete I-9 Employment Eligibility Verification",     1),
    ("HR Documents",        "Sign W-4 Federal Tax Withholding Form",                2),
    ("HR Documents",        "Complete state tax withholding form",                  3),
    ("HR Documents",        "Sign offer letter and employment agreement",            4),
    ("Payroll Setup",       "Set up direct deposit (bank account details)",          5),
    ("Payroll Setup",       "Enroll in health insurance plan",                       6),
    ("Payroll Setup",       "Set 401(k) contribution percentage",                   7),
    ("Payroll Setup",       "Submit emergency contact information",                  8),
    ("IT Setup",            "Provide government-issued photo ID",                    9),
    ("IT Setup",            "Receive company laptop / equipment",                    10),
    ("IT Setup",            "Set up company email account",                          11),
    ("IT Setup",            "Complete security awareness training",                  12),
    ("First Week",          "Complete company orientation",                           13),
    ("First Week",          "Meet with direct manager",                              14),
    ("First Week",          "Review employee handbook",                              15),
    ("First Week",          "Complete role-specific training",                       16),
    ("30-Day Check-in",     "30-day performance check-in with manager",              17),
    ("90-Day Check-in",     "90-day review and probation completion",                18),
]


# ── Models ─────────────────────────────────────────────────────
class OnboardingTask(Base):
    __tablename__ = "onboarding_tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    category = Column(String(100))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    is_required = Column(Boolean, default=True)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(255), nullable=True)
    due_days = Column(Integer, default=7)  # due N days after hire
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Schemas ────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    category: str
    title: str
    description: Optional[str] = None
    sort_order: int = 0
    is_required: bool = True
    due_days: int = 7


class TaskComplete(BaseModel):
    completed_by: str = ""


# ── Routes ─────────────────────────────────────────────────────
@router.post("/employees/{employee_id}/initialize")
async def initialize_onboarding(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create the default onboarding checklist for a new employee."""
    # Check no existing tasks
    existing = await db.execute(
        select(OnboardingTask).where(OnboardingTask.employee_id == employee_id).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Onboarding already initialized for this employee")

    tasks = []
    for category, title, order in DEFAULT_TASKS:
        task = OnboardingTask(
            employee_id=employee_id,
            company_id=current_user["company_id"],
            category=category,
            title=title,
            sort_order=order,
            due_days=3 if order <= 4 else 7 if order <= 12 else 30 if order <= 16 else 90,
        )
        db.add(task)
        tasks.append(task)

    await db.commit()
    return {"message": f"Created {len(tasks)} onboarding tasks", "count": len(tasks)}


@router.get("/employees/{employee_id}")
async def get_onboarding(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(OnboardingTask)
        .where(
            OnboardingTask.employee_id == employee_id,
            OnboardingTask.company_id == current_user["company_id"],
        )
        .order_by(OnboardingTask.sort_order)
    )
    tasks = result.scalars().all()
    if not tasks:
        return {"employee_id": employee_id, "tasks": [], "progress": 0, "complete": False}

    completed = sum(1 for t in tasks if t.completed)
    progress = round(completed / len(tasks) * 100)

    # Group by category
    categories: dict = {}
    for t in tasks:
        cat = t.category or "General"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(_ser_task(t))

    return {
        "employee_id": employee_id,
        "total": len(tasks),
        "completed": completed,
        "remaining": len(tasks) - completed,
        "progress_pct": progress,
        "complete": completed == len(tasks),
        "categories": [
            {"category": cat, "tasks": tasks_list}
            for cat, tasks_list in categories.items()
        ],
    }


@router.put("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    body: TaskComplete,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(OnboardingTask).where(
            OnboardingTask.id == task_id,
            OnboardingTask.company_id == current_user["company_id"],
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")

    task.completed = True
    task.completed_at = datetime.utcnow()
    task.completed_by = body.completed_by or current_user.get("email", "")
    await db.commit()
    await db.refresh(task)
    return _ser_task(task)


@router.put("/tasks/{task_id}/uncomplete")
async def uncomplete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(OnboardingTask).where(
            OnboardingTask.id == task_id,
            OnboardingTask.company_id == current_user["company_id"],
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    task.completed = False
    task.completed_at = None
    task.completed_by = None
    await db.commit()
    await db.refresh(task)
    return _ser_task(task)


@router.post("/tasks", status_code=201)
async def add_custom_task(
    employee_id: str,
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    task = OnboardingTask(
        employee_id=employee_id,
        company_id=current_user["company_id"],
        **body.model_dump(),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return _ser_task(task)


@router.get("/pending")
async def pending_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all employees with incomplete onboarding."""
    from sqlalchemy import func as sqlfunc
    result = await db.execute(
        select(
            OnboardingTask.employee_id,
            sqlfunc.count(OnboardingTask.id).label("total"),
            sqlfunc.sum(sqlfunc.cast(OnboardingTask.completed, Integer)).label("done"),
        )
        .where(OnboardingTask.company_id == current_user["company_id"])
        .group_by(OnboardingTask.employee_id)
        .having(sqlfunc.sum(sqlfunc.cast(OnboardingTask.completed, Integer)) <
                sqlfunc.count(OnboardingTask.id))
    )
    rows = result.all()
    return [
        {
            "employee_id": str(r.employee_id),
            "total": r.total,
            "completed": int(r.done or 0),
            "remaining": r.total - int(r.done or 0),
            "progress_pct": round(int(r.done or 0) / r.total * 100),
        }
        for r in rows
    ]


def _ser_task(t: OnboardingTask) -> dict:
    return {
        "id": str(t.id),
        "category": t.category,
        "title": t.title,
        "description": t.description,
        "sort_order": t.sort_order,
        "is_required": t.is_required,
        "completed": t.completed,
        "completed_at": str(t.completed_at) if t.completed_at else None,
        "completed_by": t.completed_by,
        "due_days": t.due_days,
    }
