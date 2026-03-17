"""
Benefits enrollment engine.
Manages benefit plans, open enrollment windows, and employee elections.

Plans: health, dental, vision, life, disability, 401k, FSA/HSA
Enrollment windows: annual open enrollment + new hire 30-day window
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Numeric, Boolean, Date, DateTime, Integer, ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/benefits", tags=["benefits"])


# ── Models ──────────────────────────────────────────────────────
class BenefitPlan(Base):
    __tablename__ = "benefit_plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    plan_type = Column(String(30), nullable=False)   # health|dental|vision|life|disability|401k|fsa|hsa
    plan_name = Column(String(100), nullable=False)
    carrier = Column(String(100))
    plan_code = Column(String(50))
    employee_cost_per_period = Column(Numeric(10, 2), default=0)
    employer_cost_per_period = Column(Numeric(10, 2), default=0)
    coverage_tier = Column(String(30), default="employee_only")  # employee_only|employee_spouse|family
    details = Column(JSONB, default=dict)            # deductible, OOP max, etc.
    is_active = Column(Boolean, default=True)
    effective_date = Column(Date)
    termination_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class EnrollmentWindow(Base):
    __tablename__ = "enrollment_windows"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)          # "2026 Open Enrollment"
    window_type = Column(String(30), default="annual")  # annual|new_hire|qualifying_event
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    effective_date = Column(Date, nullable=False)        # when elected coverage starts
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class BenefitElection(Base):
    __tablename__ = "benefit_elections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    plan_id = Column(UUID(as_uuid=True), ForeignKey("benefit_plans.id"))
    enrollment_window_id = Column(UUID(as_uuid=True), ForeignKey("enrollment_windows.id"))
    coverage_tier = Column(String(30), default="employee_only")
    employee_contribution = Column(Numeric(10, 2), default=0)
    employer_contribution = Column(Numeric(10, 2), default=0)
    status = Column(String(20), default="active")   # active|waived|terminated
    effective_date = Column(Date)
    termination_date = Column(Date)
    dependents = Column(JSONB, default=list)
    elected_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Schemas ──────────────────────────────────────────────────────
class PlanCreate(BaseModel):
    plan_type: str
    plan_name: str
    carrier: Optional[str] = None
    plan_code: Optional[str] = None
    employee_cost_per_period: float = 0
    employer_cost_per_period: float = 0
    coverage_tier: str = "employee_only"
    details: dict = {}
    effective_date: Optional[date] = None


class WindowCreate(BaseModel):
    name: str
    window_type: str = "annual"
    start_date: date
    end_date: date
    effective_date: date


class ElectionCreate(BaseModel):
    employee_id: str
    plan_id: str
    enrollment_window_id: Optional[str] = None
    coverage_tier: str = "employee_only"
    dependents: list = []


# ── Routes ──────────────────────────────────────────────────────
@router.get("/plans")
async def list_plans(
    plan_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(BenefitPlan).where(
        BenefitPlan.company_id == current_user["company_id"],
        BenefitPlan.is_active == True,
    )
    if plan_type:
        q = q.where(BenefitPlan.plan_type == plan_type)
    q = q.order_by(BenefitPlan.plan_type, BenefitPlan.plan_name)
    result = await db.execute(q)
    plans = result.scalars().all()
    return [_ser_plan(p) for p in plans]


@router.post("/plans", status_code=201)
async def create_plan(
    body: PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    VALID_TYPES = {"health", "dental", "vision", "life", "disability", "401k", "fsa", "hsa"}
    if body.plan_type not in VALID_TYPES:
        raise HTTPException(400, f"plan_type must be one of: {', '.join(sorted(VALID_TYPES))}")
    plan = BenefitPlan(company_id=current_user["company_id"], **body.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return _ser_plan(plan)


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    body: PlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(BenefitPlan).where(
            BenefitPlan.id == plan_id,
            BenefitPlan.company_id == current_user["company_id"],
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(plan, k, v)
    await db.commit()
    await db.refresh(plan)
    return _ser_plan(plan)


@router.get("/windows")
async def list_windows(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(EnrollmentWindow)
        .where(EnrollmentWindow.company_id == current_user["company_id"])
        .order_by(EnrollmentWindow.start_date.desc())
    )
    windows = result.scalars().all()
    today = date.today()
    return [
        {
            **_ser_window(w),
            "is_open": w.start_date <= today <= w.end_date,
            "days_remaining": max(0, (w.end_date - today).days) if today <= w.end_date else 0,
        }
        for w in windows
    ]


@router.post("/windows", status_code=201)
async def create_window(
    body: WindowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.end_date < body.start_date:
        raise HTTPException(400, "end_date must be after start_date")
    window = EnrollmentWindow(company_id=current_user["company_id"], **body.model_dump())
    db.add(window)
    await db.commit()
    await db.refresh(window)
    return _ser_window(window)


@router.get("/elections")
async def list_elections(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(BenefitElection).where(BenefitElection.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(BenefitElection.employee_id == employee_id)
    if status:
        q = q.where(BenefitElection.status == status)
    q = q.order_by(BenefitElection.elected_at.desc())
    result = await db.execute(q)
    return [_ser_election(e) for e in result.scalars().all()]


@router.post("/elections", status_code=201)
async def create_election(
    body: ElectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Get plan details
    plan_res = await db.execute(
        select(BenefitPlan).where(BenefitPlan.id == body.plan_id)
    )
    plan = plan_res.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")

    # Deactivate any existing election for same plan type
    existing_res = await db.execute(
        select(BenefitElection).where(
            BenefitElection.employee_id == body.employee_id,
            BenefitElection.company_id == current_user["company_id"],
            BenefitElection.status == "active",
        )
    )
    for existing in existing_res.scalars().all():
        plan_check_res = await db.execute(
            select(BenefitPlan).where(BenefitPlan.id == existing.plan_id)
        )
        plan_check = plan_check_res.scalar_one_or_none()
        if plan_check and plan_check.plan_type == plan.plan_type:
            existing.status = "terminated"
            existing.termination_date = date.today()

    election = BenefitElection(
        company_id=current_user["company_id"],
        employee_contribution=float(plan.employee_cost_per_period),
        employer_contribution=float(plan.employer_cost_per_period),
        **body.model_dump(),
    )
    db.add(election)

    # Update employee's benefit deductions
    await _sync_employee_deductions(db, body.employee_id, current_user["company_id"])

    await db.commit()
    await db.refresh(election)
    return _ser_election(election)


@router.delete("/elections/{election_id}", status_code=204)
async def waive_election(
    election_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(BenefitElection).where(
            BenefitElection.id == election_id,
            BenefitElection.company_id == current_user["company_id"],
        )
    )
    election = result.scalar_one_or_none()
    if not election:
        raise HTTPException(404, "Election not found")
    election.status = "waived"
    election.termination_date = date.today()
    await _sync_employee_deductions(db, str(election.employee_id), current_user["company_id"])
    await db.commit()


@router.get("/summary/employee/{employee_id}")
async def employee_benefits_summary(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Full benefits cost breakdown for one employee."""
    elections_res = await db.execute(
        select(BenefitElection).where(
            BenefitElection.employee_id == employee_id,
            BenefitElection.company_id == current_user["company_id"],
            BenefitElection.status == "active",
        )
    )
    elections = elections_res.scalars().all()

    total_emp = sum(float(e.employee_contribution or 0) for e in elections)
    total_er = sum(float(e.employer_contribution or 0) for e in elections)

    enrolled_plans = []
    for e in elections:
        plan_res = await db.execute(select(BenefitPlan).where(BenefitPlan.id == e.plan_id))
        plan = plan_res.scalar_one_or_none()
        if plan:
            enrolled_plans.append({
                "plan_type": plan.plan_type,
                "plan_name": plan.plan_name,
                "carrier": plan.carrier,
                "coverage_tier": e.coverage_tier,
                "employee_cost": float(e.employee_contribution),
                "employer_cost": float(e.employer_contribution),
                "status": e.status,
            })

    return {
        "employee_id": employee_id,
        "enrolled_plans": enrolled_plans,
        "total_employee_cost_per_period": round(total_emp, 2),
        "total_employer_cost_per_period": round(total_er, 2),
        "total_cost_per_period": round(total_emp + total_er, 2),
        "annual_employee_cost": round(total_emp * 26, 2),
        "annual_employer_cost": round(total_er * 26, 2),
    }


async def _sync_employee_deductions(db, employee_id, company_id):
    """Sync employee benefit deductions from active elections."""
    from models import Employee
    elections_res = await db.execute(
        select(BenefitElection, BenefitPlan)
        .join(BenefitPlan, BenefitElection.plan_id == BenefitPlan.id)
        .where(
            BenefitElection.employee_id == employee_id,
            BenefitElection.company_id == company_id,
            BenefitElection.status == "active",
        )
    )
    rows = elections_res.all()

    health = dental = vision = hsa = 0.0
    for election, plan in rows:
        cost = float(election.employee_contribution or 0)
        if plan.plan_type == "health":   health += cost
        elif plan.plan_type == "dental": dental += cost
        elif plan.plan_type == "vision": vision += cost
        elif plan.plan_type in ("hsa", "fsa"): hsa += cost

    emp_res = await db.execute(select(Employee).where(Employee.id == employee_id))
    emp = emp_res.scalar_one_or_none()
    if emp:
        emp.health_insurance_deduction = health
        emp.dental_deduction = dental
        emp.vision_deduction = vision
        emp.hsa_deduction = hsa


def _ser_plan(p: BenefitPlan) -> dict:
    return {
        "id": str(p.id), "plan_type": p.plan_type, "plan_name": p.plan_name,
        "carrier": p.carrier, "plan_code": p.plan_code,
        "employee_cost_per_period": float(p.employee_cost_per_period),
        "employer_cost_per_period": float(p.employer_cost_per_period),
        "coverage_tier": p.coverage_tier, "details": p.details or {},
        "is_active": p.is_active,
        "effective_date": str(p.effective_date) if p.effective_date else None,
    }

def _ser_window(w: EnrollmentWindow) -> dict:
    return {
        "id": str(w.id), "name": w.name, "window_type": w.window_type,
        "start_date": str(w.start_date), "end_date": str(w.end_date),
        "effective_date": str(w.effective_date), "is_active": w.is_active,
    }

def _ser_election(e: BenefitElection) -> dict:
    return {
        "id": str(e.id), "employee_id": str(e.employee_id),
        "plan_id": str(e.plan_id), "coverage_tier": e.coverage_tier,
        "employee_contribution": float(e.employee_contribution or 0),
        "employer_contribution": float(e.employer_contribution or 0),
        "status": e.status,
        "effective_date": str(e.effective_date) if e.effective_date else None,
        "elected_at": str(e.elected_at),
    }
