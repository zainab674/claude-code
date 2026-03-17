import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import OnboardingTask
from utils.auth import get_current_user
from uuid import UUID

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
    current_user: dict = Depends(get_current_user),
):
    """Create the default onboarding checklist for a new employee."""
    # Check no existing tasks
    existing = await OnboardingTask.find_one(OnboardingTask.employee_id == UUID(employee_id))
    if existing:
        raise HTTPException(409, "Onboarding already initialized for this employee")

    for category, title, order in DEFAULT_TASKS:
        task = OnboardingTask(
            employee_id=UUID(employee_id),
            company_id=current_user["company_id"],
            category=category,
            title=title,
            sort_order=order,
            due_days=3 if order <= 4 else 7 if order <= 12 else 30 if order <= 16 else 90,
        )
        await task.insert()

    return {"message": "Created onboarding tasks", "count": len(DEFAULT_TASKS)}


@router.get("/employees/{employee_id}")
async def get_onboarding(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    tasks = await OnboardingTask.find(
        OnboardingTask.employee_id == UUID(employee_id),
        OnboardingTask.company_id == current_user["company_id"],
    ).sort("sort_order").to_list()
    
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
    current_user: dict = Depends(get_current_user),
):
    task = await OnboardingTask.find_one(
        OnboardingTask.id == UUID(task_id),
        OnboardingTask.company_id == current_user["company_id"],
    )
    if not task:
        raise HTTPException(404, "Task not found")

    task.completed = True
    task.completed_at = datetime.utcnow()
    task.completed_by = body.completed_by or current_user.get("email", "")
    await task.save()
    return _ser_task(task)


@router.put("/tasks/{task_id}/uncomplete")
async def uncomplete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    task = await OnboardingTask.find_one(
        OnboardingTask.id == UUID(task_id),
        OnboardingTask.company_id == current_user["company_id"],
    )
    if not task:
        raise HTTPException(404, "Task not found")
    task.completed = False
    task.completed_at = None
    task.completed_by = None
    await task.save()
    return _ser_task(task)


@router.post("/tasks", status_code=201)
async def add_custom_task(
    employee_id: str,
    body: TaskCreate,
    current_user: dict = Depends(get_current_user),
):
    task = OnboardingTask(
        employee_id=UUID(employee_id),
        company_id=current_user["company_id"],
        **body.model_dump(),
    )
    await task.insert()
    return _ser_task(task)


@router.get("/pending")
async def pending_onboarding(
    current_user: dict = Depends(get_current_user),
):
    """List all employees with incomplete onboarding."""
    pipeline = [
        {"$match": {"company_id": current_user["company_id"]}},
        {"$group": {
            "_id": "$employee_id",
            "total": {"$sum": 1},
            "done": {"$sum": {"$cond": [{"$eq": ["$completed", True]}, 1, 0]}}
        }},
        {"$match": {"$expr": {"$lt": ["$done", "$total"]}}}
    ]
    
    rows = await OnboardingTask.aggregate(pipeline).to_list()
    return [
        {
            "employee_id": str(r["_id"]),
            "total": r["total"],
            "completed": int(r["done"] or 0),
            "remaining": r["total"] - int(r["done"] or 0),
            "progress_pct": round(int(r["done"] or 0) / r["total"] * 100),
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
