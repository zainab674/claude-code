"""
Performance review system.
Supports: annual reviews, 90-day reviews, pip (performance improvement plans).

Review cycles → Reviews (one per employee per cycle) → Ratings → Goals
"""
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import ReviewCycle, PerformanceReview, ReviewGoal, Employee
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/performance", tags=["performance"])

RATING_SCALE = {
    1: "Needs Improvement",
    2: "Below Expectations",
    3: "Meets Expectations",
    4: "Exceeds Expectations",
    5: "Exceptional"
}


# ── Schemas ────────────────────────────────────────────────────
class CycleCreate(BaseModel):
    name: str
    cycle_type: str = "annual"
    review_period_start: date
    review_period_end: date
    due_date: date
    include_self_review: bool = True


class ReviewUpdate(BaseModel):
    overall_rating: Optional[float] = None
    strengths: Optional[str] = None
    areas_for_improvement: Optional[str] = None
    ratings: dict = {}
    goals_next_period: Optional[str] = None


class GoalCreate(BaseModel):
    employee_id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    category: str = "professional"


# ── Routes: Cycles ─────────────────────────────────────────────
@router.get("/cycles")
async def list_cycles(
    current_user: dict = Depends(get_current_user),
):
    cycles = await ReviewCycle.find(
        ReviewCycle.company_id == current_user["company_id"]
    ).sort("-created_at").to_list()
    return [_ser_cycle(c) for c in cycles]


@router.post("/cycles", status_code=201)
async def create_cycle(
    body: CycleCreate,
    current_user: dict = Depends(get_current_user),
):
    cycle = ReviewCycle(
        company_id=current_user["company_id"],
        name=body.name,
        cycle_type=body.cycle_type,
        review_period_start=datetime.combine(body.review_period_start, datetime.min.time()),
        review_period_end=datetime.combine(body.review_period_end, datetime.min.time()),
        due_date=datetime.combine(body.due_date, datetime.min.time()),
        include_self_review=body.include_self_review,
        status="active"
    )
    await cycle.insert()

    # Automatically create pending reviews for all active employees
    employees = await Employee.find(
        Employee.company_id == cycle.company_id,
        Employee.status == "active"
    ).to_list()

    reviews = []
    for emp in employees:
        review = PerformanceReview(
            cycle_id=cycle.id,
            company_id=cycle.company_id,
            employee_id=emp.id,
            status="pending",
        )
        reviews.append(review)
    
    if reviews:
        await PerformanceReview.insert_many(reviews)

    return _ser_cycle(cycle)


# ── Routes: Reviews ────────────────────────────────────────────
@router.get("/reviews")
async def list_reviews(
    cycle_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if cycle_id:
        query["cycle_id"] = UUID(cycle_id)
    if employee_id:
        query["employee_id"] = UUID(employee_id)
    
    reviews = await PerformanceReview.find(query).to_list()
    out = []
    for r in reviews:
        emp = await Employee.find_one(Employee.id == r.employee_id)
        out.append({
            **_ser_review(r),
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
        })
    return out


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: str,
    current_user: dict = Depends(get_current_user),
):
    review = await PerformanceReview.find_one(
        PerformanceReview.id == UUID(review_id),
        PerformanceReview.company_id == current_user["company_id"]
    )
    if not review:
        raise HTTPException(404, "Review not found")
    return _ser_review(review)


@router.put("/reviews/{review_id}")
async def update_review(
    review_id: str,
    body: ReviewUpdate,
    current_user: dict = Depends(get_current_user),
):
    review = await PerformanceReview.find_one(
        PerformanceReview.id == UUID(review_id),
        PerformanceReview.company_id == current_user["company_id"]
    )
    if not review:
        raise HTTPException(404, "Review not found")

    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(review, k, v)
    
    if review.status == "pending":
        review.status = "in_progress"
    
    await review.save()
    return _ser_review(review)


@router.post("/reviews/{review_id}/submit")
async def submit_review(
    review_id: str,
    current_user: dict = Depends(get_current_user),
):
    review = await PerformanceReview.find_one(
        PerformanceReview.id == UUID(review_id),
        PerformanceReview.company_id == current_user["company_id"]
    )
    if not review:
        raise HTTPException(404, "Review not found")

    review.status = "submitted"
    review.submitted_at = datetime.utcnow()
    await review.save()
    return {"message": "Review submitted"}


# ── Routes: Goals ──────────────────────────────────────────────
@router.get("/goals")
async def list_goals(
    employee_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = UUID(employee_id)
    
    goals = await ReviewGoal.find(query).sort("-created_at").to_list()
    return [_ser_goal(g) for g in goals]


@router.post("/goals", status_code=201)
async def create_goal(
    body: GoalCreate,
    current_user: dict = Depends(get_current_user),
):
    goal = ReviewGoal(
        company_id=current_user["company_id"],
        employee_id=UUID(body.employee_id),
        title=body.title,
        description=body.description,
        due_date=datetime.combine(body.due_date, datetime.min.time()) if body.due_date else None,
        category=body.category,
        status="active"
    )
    await goal.insert()
    return _ser_goal(goal)


@router.put("/goals/{goal_id}/progress")
async def update_goal_progress(
    goal_id: str,
    progress_pct: int,
    current_user: dict = Depends(get_current_user),
):
    goal = await ReviewGoal.find_one(
        ReviewGoal.id == UUID(goal_id),
        ReviewGoal.company_id == current_user["company_id"]
    )
    if not goal:
        raise HTTPException(404, "Goal not found")
        
    goal.progress_pct = max(0, min(100, progress_pct))
    if goal.progress_pct == 100:
        goal.status = "completed"
        goal.completed_at = datetime.utcnow()
    
    await goal.save()
    return _ser_goal(goal)


@router.get("/summary/{employee_id}")
async def employee_performance_summary(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Performance overview for one employee."""
    emp_uuid = UUID(employee_id)
    company_id = current_user["company_id"]
    
    reviews = await PerformanceReview.find(
        PerformanceReview.employee_id == emp_uuid,
        PerformanceReview.company_id == company_id,
        PerformanceReview.status == "submitted",
    ).sort("-submitted_at").limit(5).to_list()

    goals = await ReviewGoal.find(
        ReviewGoal.employee_id == emp_uuid,
        ReviewGoal.company_id == company_id,
    ).to_list()

    avg_rating = None
    rated = [float(r.overall_rating) for r in reviews if r.overall_rating]
    if rated:
        avg_rating = round(sum(rated) / len(rated), 1)

    return {
        "employee_id": employee_id,
        "review_count": len(reviews),
        "average_rating": avg_rating,
        "rating_label": RATING_SCALE.get(round(avg_rating) if avg_rating else 0, "—"),
        "total_goals": len(goals),
        "completed_goals": sum(1 for g in goals if g.status == "completed"),
        "active_goals": sum(1 for g in goals if g.status == "active"),
        "recent_reviews": [_ser_review(r) for r in reviews[:3]],
        "goals": [_ser_goal(g) for g in goals if g.status == "active"],
    }


# ── Serializers ────────────────────────────────────────────────
def _ser_cycle(c: ReviewCycle) -> dict:
    return {
        "id": str(c.id), "name": c.name, "cycle_type": c.cycle_type,
        "review_period_start": str(c.review_period_start.date()) if isinstance(c.review_period_start, datetime) else str(c.review_period_start),
        "review_period_end": str(c.review_period_end.date()) if isinstance(c.review_period_end, datetime) else str(c.review_period_end),
        "due_date": str(c.due_date.date()) if isinstance(c.due_date, datetime) else str(c.due_date),
        "status": c.status, "include_self_review": c.include_self_review,
        "created_at": str(c.created_at),
    }

def _ser_review(r: PerformanceReview) -> dict:
    rating = float(r.overall_rating) if r.overall_rating else 0
    return {
        "id": str(r.id), "cycle_id": str(r.cycle_id),
        "employee_id": str(r.employee_id),
        "reviewer_id": str(r.reviewer_id) if r.reviewer_id else None,
        "status": r.status,
        "overall_rating": float(r.overall_rating) if r.overall_rating else None,
        "rating_label": RATING_SCALE.get(round(rating), "—"),
        "strengths": r.strengths, "areas_for_improvement": r.areas_for_improvement,
        "ratings": r.ratings or {},
        "goals_next_period": r.goals_next_period,
        "submitted_at": str(r.submitted_at) if r.submitted_at else None,
    }

def _ser_goal(g: ReviewGoal) -> dict:
    return {
        "id": str(g.id), "employee_id": str(g.employee_id),
        "title": g.title, "description": g.description,
        "due_date": str(g.due_date.date()) if isinstance(g.due_date, datetime) else str(g.due_date),
        "status": g.status, "progress_pct": g.progress_pct,
        "category": g.category,
        "completed_at": str(g.completed_at) if g.completed_at else None,
    }
