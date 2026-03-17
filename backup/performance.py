"""
Performance review system.
Supports: annual reviews, 90-day reviews, pip (performance improvement plans).

Review cycles → Reviews (one per employee per cycle) → Ratings → Goals
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (Column, String, Numeric, Integer, Boolean,
                        Date, DateTime, ForeignKey, Text, select, func)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/performance", tags=["performance"])

RATING_SCALE = {1: "Needs Improvement", 2: "Below Expectations",
                3: "Meets Expectations", 4: "Exceeds Expectations", 5: "Outstanding"}


# ── Models ─────────────────────────────────────────────────────
class ReviewCycle(Base):
    __tablename__ = "review_cycles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    name = Column(String(150), nullable=False)
    cycle_type = Column(String(30), default="annual")  # annual|quarterly|90day|pip
    review_period_start = Column(Date)
    review_period_end = Column(Date)
    due_date = Column(Date)
    status = Column(String(20), default="draft")  # draft|active|completed
    include_self_review = Column(Boolean, default=True)
    include_peer_review = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PerformanceReview(Base):
    __tablename__ = "performance_reviews"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle_id = Column(UUID(as_uuid=True), ForeignKey("review_cycles.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    review_type = Column(String(20), default="manager")  # manager|self|peer
    status = Column(String(20), default="pending")  # pending|in_progress|submitted|acknowledged
    overall_rating = Column(Numeric(3, 1))  # 1.0 – 5.0
    strengths = Column(Text)
    areas_for_improvement = Column(Text)
    manager_comments = Column(Text)
    employee_comments = Column(Text)  # employee acknowledgment note
    ratings = Column(JSONB, default=dict)  # {category: rating}
    goals_next_period = Column(Text)
    recommended_raise_pct = Column(Numeric(5, 2))
    recommended_promotion = Column(Boolean, default=False)
    submitted_at = Column(DateTime(timezone=True))
    acknowledged_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ReviewGoal(Base):
    __tablename__ = "review_goals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    review_id = Column(UUID(as_uuid=True), ForeignKey("performance_reviews.id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    due_date = Column(Date)
    status = Column(String(20), default="active")  # active|completed|cancelled
    progress_pct = Column(Integer, default=0)
    category = Column(String(50), default="professional")  # professional|technical|leadership|other
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True))


# ── Schemas ────────────────────────────────────────────────────
class CycleCreate(BaseModel):
    name: str
    cycle_type: str = "annual"
    review_period_start: Optional[date] = None
    review_period_end: Optional[date] = None
    due_date: Optional[date] = None
    include_self_review: bool = True
    include_peer_review: bool = False


class ReviewCreate(BaseModel):
    cycle_id: str
    employee_id: str
    reviewer_id: Optional[str] = None
    review_type: str = "manager"


class ReviewUpdate(BaseModel):
    overall_rating: Optional[float] = None
    strengths: Optional[str] = None
    areas_for_improvement: Optional[str] = None
    manager_comments: Optional[str] = None
    employee_comments: Optional[str] = None
    ratings: Optional[dict] = None
    goals_next_period: Optional[str] = None
    recommended_raise_pct: Optional[float] = None
    recommended_promotion: Optional[bool] = None


class GoalCreate(BaseModel):
    employee_id: str
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    category: str = "professional"


# ── Routes: Cycles ─────────────────────────────────────────────
@router.get("/cycles")
async def list_cycles(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(ReviewCycle)
        .where(ReviewCycle.company_id == current_user["company_id"])
        .order_by(ReviewCycle.created_at.desc())
    )
    return [_ser_cycle(c) for c in result.scalars().all()]


@router.post("/cycles", status_code=201)
async def create_cycle(
    body: CycleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cycle = ReviewCycle(company_id=current_user["company_id"], **body.model_dump())
    db.add(cycle)
    await db.commit()
    await db.refresh(cycle)
    return _ser_cycle(cycle)


@router.post("/cycles/{cycle_id}/launch")
async def launch_cycle(
    cycle_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Launch a cycle — creates a review record for every active employee."""
    cycle_res = await db.execute(
        select(ReviewCycle).where(
            ReviewCycle.id == cycle_id,
            ReviewCycle.company_id == current_user["company_id"],
        )
    )
    cycle = cycle_res.scalar_one_or_none()
    if not cycle:
        raise HTTPException(404, "Cycle not found")
    if cycle.status == "active":
        raise HTTPException(400, "Cycle already launched")

    from models import Employee
    emp_res = await db.execute(
        select(Employee).where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
    )
    employees = emp_res.scalars().all()
    created = 0
    for emp in employees:
        review = PerformanceReview(
            cycle_id=cycle.id,
            company_id=cycle.company_id,
            employee_id=emp.id,
            review_type="manager",
        )
        db.add(review)
        if cycle.include_self_review:
            self_review = PerformanceReview(
                cycle_id=cycle.id,
                company_id=cycle.company_id,
                employee_id=emp.id,
                review_type="self",
            )
            db.add(self_review)
        created += 1

    cycle.status = "active"
    await db.commit()
    return {"message": f"Cycle launched — {created} reviews created", "employee_count": created}


# ── Routes: Reviews ────────────────────────────────────────────
@router.get("/reviews")
async def list_reviews(
    cycle_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(PerformanceReview).where(
        PerformanceReview.company_id == current_user["company_id"]
    )
    if cycle_id:   q = q.where(PerformanceReview.cycle_id == cycle_id)
    if employee_id: q = q.where(PerformanceReview.employee_id == employee_id)
    if status:     q = q.where(PerformanceReview.status == status)
    q = q.order_by(PerformanceReview.created_at.desc())
    result = await db.execute(q)
    return [_ser_review(r) for r in result.scalars().all()]


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PerformanceReview).where(
            PerformanceReview.id == review_id,
            PerformanceReview.company_id == current_user["company_id"],
        )
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Review not found")
    return _ser_review(r)


@router.put("/reviews/{review_id}")
async def update_review(
    review_id: str,
    body: ReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PerformanceReview).where(
            PerformanceReview.id == review_id,
            PerformanceReview.company_id == current_user["company_id"],
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(404, "Review not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(review, k, v)
    review.status = "in_progress"
    await db.commit()
    await db.refresh(review)
    return _ser_review(review)


@router.post("/reviews/{review_id}/submit")
async def submit_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PerformanceReview).where(
            PerformanceReview.id == review_id,
            PerformanceReview.company_id == current_user["company_id"],
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(404, "Review not found")
    review.status = "submitted"
    review.submitted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Review submitted", "submitted_at": str(review.submitted_at)}


@router.post("/reviews/{review_id}/acknowledge")
async def acknowledge_review(
    review_id: str,
    comments: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Employee acknowledges receiving their review."""
    result = await db.execute(
        select(PerformanceReview).where(
            PerformanceReview.id == review_id,
            PerformanceReview.company_id == current_user["company_id"],
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(404, "Review not found")
    review.status = "acknowledged"
    review.acknowledged_at = datetime.utcnow()
    if comments:
        review.employee_comments = comments
    await db.commit()
    return {"message": "Review acknowledged"}


# ── Routes: Goals ──────────────────────────────────────────────
@router.get("/goals")
async def list_goals(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(ReviewGoal).where(ReviewGoal.company_id == current_user["company_id"])
    if employee_id: q = q.where(ReviewGoal.employee_id == employee_id)
    if status:      q = q.where(ReviewGoal.status == status)
    q = q.order_by(ReviewGoal.due_date)
    result = await db.execute(q)
    return [_ser_goal(g) for g in result.scalars().all()]


@router.post("/goals", status_code=201)
async def create_goal(
    body: GoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    goal = ReviewGoal(company_id=current_user["company_id"], **body.model_dump())
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return _ser_goal(goal)


@router.put("/goals/{goal_id}/progress")
async def update_goal_progress(
    goal_id: str,
    progress_pct: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(ReviewGoal).where(
            ReviewGoal.id == goal_id,
            ReviewGoal.company_id == current_user["company_id"],
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(404, "Goal not found")
    goal.progress_pct = max(0, min(100, progress_pct))
    if goal.progress_pct == 100:
        goal.status = "completed"
        goal.completed_at = datetime.utcnow()
    await db.commit()
    return _ser_goal(goal)


@router.get("/summary/{employee_id}")
async def employee_performance_summary(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Performance overview for one employee."""
    reviews_res = await db.execute(
        select(PerformanceReview).where(
            PerformanceReview.employee_id == employee_id,
            PerformanceReview.company_id == current_user["company_id"],
            PerformanceReview.status == "submitted",
        ).order_by(PerformanceReview.submitted_at.desc()).limit(5)
    )
    reviews = reviews_res.scalars().all()

    goals_res = await db.execute(
        select(ReviewGoal).where(
            ReviewGoal.employee_id == employee_id,
            ReviewGoal.company_id == current_user["company_id"],
        )
    )
    goals = goals_res.scalars().all()

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
        "review_period_start": str(c.review_period_start) if c.review_period_start else None,
        "review_period_end": str(c.review_period_end) if c.review_period_end else None,
        "due_date": str(c.due_date) if c.due_date else None,
        "status": c.status, "include_self_review": c.include_self_review,
        "include_peer_review": c.include_peer_review,
        "created_at": str(c.created_at),
    }

def _ser_review(r: PerformanceReview) -> dict:
    return {
        "id": str(r.id), "cycle_id": str(r.cycle_id),
        "employee_id": str(r.employee_id),
        "reviewer_id": str(r.reviewer_id) if r.reviewer_id else None,
        "review_type": r.review_type, "status": r.status,
        "overall_rating": float(r.overall_rating) if r.overall_rating else None,
        "rating_label": RATING_SCALE.get(round(float(r.overall_rating)) if r.overall_rating else 0),
        "strengths": r.strengths, "areas_for_improvement": r.areas_for_improvement,
        "manager_comments": r.manager_comments, "employee_comments": r.employee_comments,
        "ratings": r.ratings or {},
        "goals_next_period": r.goals_next_period,
        "recommended_raise_pct": float(r.recommended_raise_pct) if r.recommended_raise_pct else None,
        "recommended_promotion": r.recommended_promotion,
        "submitted_at": str(r.submitted_at) if r.submitted_at else None,
        "acknowledged_at": str(r.acknowledged_at) if r.acknowledged_at else None,
    }

def _ser_goal(g: ReviewGoal) -> dict:
    return {
        "id": str(g.id), "employee_id": str(g.employee_id),
        "title": g.title, "description": g.description,
        "due_date": str(g.due_date) if g.due_date else None,
        "status": g.status, "progress_pct": g.progress_pct,
        "category": g.category,
        "completed_at": str(g.completed_at) if g.completed_at else None,
    }
