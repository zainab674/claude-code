"""
Benefits enrollment engine.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import Employee, BenefitPlan, EnrollmentWindow, BenefitElection
from utils.auth import get_current_user

router = APIRouter(prefix="/benefits", tags=["benefits"])


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
    current_user: dict = Depends(get_current_user),
):
    query = {
        "company_id": current_user["company_id"],
        "is_active": True,
    }
    if plan_type:
        query["plan_type"] = plan_type
    
    plans = await BenefitPlan.find(query).sort("plan_type", "plan_name").to_list()
    return [_ser_plan(p) for p in plans]


@router.post("/plans", status_code=201)
async def create_plan(
    body: PlanCreate,
    current_user: dict = Depends(get_current_user),
):
    VALID_TYPES = {"health", "dental", "vision", "life", "disability", "401k", "fsa", "hsa"}
    if body.plan_type not in VALID_TYPES:
        raise HTTPException(400, f"plan_type must be one of: {', '.join(sorted(VALID_TYPES))}")
    
    plan = BenefitPlan(
        company_id=current_user["company_id"],
        **body.model_dump()
    )
    await plan.insert()
    return _ser_plan(plan)


@router.put("/plans/{plan_id}")
async def update_plan(
    plan_id: uuid.UUID,
    body: PlanCreate,
    current_user: dict = Depends(get_current_user),
):
    plan = await BenefitPlan.find_one(
        BenefitPlan.id == plan_id,
        BenefitPlan.company_id == current_user["company_id"]
    )
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(plan, k, v)
    
    await plan.save()
    return _ser_plan(plan)


@router.get("/windows")
async def list_windows(
    current_user: dict = Depends(get_current_user),
):
    windows = await EnrollmentWindow.find(
        EnrollmentWindow.company_id == current_user["company_id"]
    ).sort("-start_date").to_list()
    
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
    current_user: dict = Depends(get_current_user),
):
    if body.end_date < body.start_date:
        raise HTTPException(400, "end_date must be after start_date")
    
    window = EnrollmentWindow(
        company_id=current_user["company_id"],
        **body.model_dump()
    )
    await window.insert()
    return _ser_window(window)


@router.get("/elections")
async def list_elections(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = uuid.UUID(employee_id)
    if status:
        query["status"] = status
    
    elections = await BenefitElection.find(query).sort("-elected_at").to_list()
    return [_ser_election(e) for e in elections]


@router.post("/elections", status_code=201)
async def create_election(
    body: ElectionCreate,
    current_user: dict = Depends(get_current_user),
):
    # Get plan details
    plan = await BenefitPlan.get(uuid.UUID(body.plan_id))
    if not plan:
        raise HTTPException(404, "Plan not found")

    company_id = current_user["company_id"]
    employee_id = uuid.UUID(body.employee_id)

    # Deactivate any existing election for same plan type
    existing_elections = await BenefitElection.find(
        BenefitElection.employee_id == employee_id,
        BenefitElection.company_id == company_id,
        BenefitElection.status == "active"
    ).to_list()
    
    for existing in existing_elections:
        plan_check = await BenefitPlan.get(existing.plan_id)
        if plan_check and plan_check.plan_type == plan.plan_type:
            existing.status = "terminated"
            existing.termination_date = date.today()
            await existing.save()

    election = BenefitElection(
        company_id=company_id,
        employee_id=employee_id,
        plan_id=plan.id,
        enrollment_window_id=uuid.UUID(body.enrollment_window_id) if body.enrollment_window_id else None,
        coverage_tier=body.coverage_tier,
        employee_contribution=plan.employee_cost_per_period,
        employer_contribution=plan.employer_cost_per_period,
        dependents=body.dependents
    )
    await election.insert()

    # Update employee's benefit deductions
    await _sync_employee_deductions(str(employee_id), str(company_id))

    return _ser_election(election)


@router.delete("/elections/{election_id}", status_code=204)
async def waive_election(
    election_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    election = await BenefitElection.find_one(
        BenefitElection.id == election_id,
        BenefitElection.company_id == current_user["company_id"]
    )
    if not election:
        raise HTTPException(404, "Election not found")
    
    election.status = "waived"
    election.termination_date = date.today()
    await election.save()
    
    await _sync_employee_deductions(str(election.employee_id), current_user["company_id"])


@router.get("/summary/employee/{employee_id}")
async def employee_benefits_summary(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Full benefits cost breakdown for one employee."""
    company_id = current_user["company_id"]
    emp_id = uuid.UUID(employee_id)
    
    elections = await BenefitElection.find(
        BenefitElection.employee_id == emp_id,
        BenefitElection.company_id == company_id,
        BenefitElection.status == "active"
    ).to_list()

    total_emp = sum(float(e.employee_contribution or 0) for e in elections)
    total_er = sum(float(e.employer_contribution or 0) for e in elections)

    enrolled_plans = []
    for e in elections:
        plan = await BenefitPlan.get(e.plan_id)
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


async def _sync_employee_deductions(employee_id: str, company_id: str):
    """Sync employee benefit deductions from active elections."""
    emp_id = uuid.UUID(employee_id)
    comp_id = uuid.UUID(company_id)
    
    elections = await BenefitElection.find(
        BenefitElection.employee_id == emp_id,
        BenefitElection.company_id == comp_id,
        BenefitElection.status == "active"
    ).to_list()

    health = dental = vision = hsa = 0.0
    for election in elections:
        plan = await BenefitPlan.get(election.plan_id)
        if not plan: continue
        
        cost = float(election.employee_contribution or 0)
        if plan.plan_type == "health":   health += cost
        elif plan.plan_type == "dental": dental += cost
        elif plan.plan_type == "vision": vision += cost
        elif plan.plan_type in ("hsa", "fsa"): hsa += cost

    emp = await Employee.get(emp_id)
    if emp:
        emp.health_insurance_deduction = health
        emp.dental_deduction = dental
        emp.vision_deduction = vision
        emp.hsa_deduction = hsa
        await emp.save()


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
