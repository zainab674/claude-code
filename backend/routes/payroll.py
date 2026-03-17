from typing import Optional, List
from uuid import UUID
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from models import Employee, PayPeriod, PayRun, PayRunItem, Paystub, Company
from services.calculator import calculator, PayCalculationInput
from services.pdf_generator import generate_paystub_pdf
from utils.auth import get_current_user
import os

router = APIRouter(prefix="/payroll", tags=["payroll"])


class HoursOverride(BaseModel):
    employee_id: str
    regular_hours: float = 80.0
    overtime_hours: float = 0.0
    double_time_hours: float = 0.0
    bonus_pay: float = 0.0
    commission_pay: float = 0.0
    reimbursement: float = 0.0


class PayrollPreviewRequest(BaseModel):
    pay_period_id: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    pay_date: Optional[date] = None
    employee_ids: Optional[List[str]] = None   # None = all active
    hours_overrides: Optional[List[HoursOverride]] = []


class PayrollRunRequest(PayrollPreviewRequest):
    notes: Optional[str] = None


# ── Preview ────────────────────────────────────────────────────────
@router.post("/preview")
async def preview_payroll(
    req: PayrollPreviewRequest,
    current_user: dict = Depends(get_current_user),
):
    employees, hours_map = await _load_employees(current_user["company_id"], req)
    items = []
    totals = {"gross": 0, "employee_taxes": 0, "employer_taxes": 0, "deductions": 0, "net": 0}

    for emp in employees:
        h = hours_map.get(str(emp.id), HoursOverride(employee_id=str(emp.id)))
        inp = _build_calc_input(emp, h)
        result = calculator.calculate(inp)
        item = _result_to_dict(str(emp.id), emp, result)
        items.append(item)
        totals["gross"] += float(result.gross_pay)
        totals["employee_taxes"] += float(result.total_employee_taxes)
        totals["employer_taxes"] += float(result.total_employer_taxes)
        totals["deductions"] += float(result.total_pretax_deductions)
        totals["net"] += float(result.net_pay)

    return {
        "preview": True,
        "employee_count": len(items),
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "items": items,
    }


# ── Run ────────────────────────────────────────────────────────────
@router.post("/run")
async def run_payroll(
    req: PayrollRunRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    # Resolve or create pay period
    pay_period = await _resolve_pay_period(current_user["company_id"], req)

    employees, hours_map = await _load_employees(current_user["company_id"], req)
    if not employees:
        raise HTTPException(status_code=400, detail="No active employees found")

    # Create pay run record
    pay_run = PayRun(
        company_id=current_user["company_id"],
        pay_period_id=pay_period.id,
        status="processing",
        created_by=current_user["sub"],
        notes=req.notes,
    )
    await pay_run.insert()

    # Calculate each employee
    run_items = []
    totals = {"gross": 0, "emp_taxes": 0, "emp_employer_taxes": 0, "deductions": 0, "net": 0}

    for emp in employees:
        h = hours_map.get(str(emp.id), HoursOverride(employee_id=str(emp.id)))
        # Get YTD from prior runs
        ytd = await _get_ytd(emp.id, pay_period.period_start)

        inp = _build_calc_input(emp, h, ytd_gross=ytd["gross"], ytd_ss_wages=ytd["social_security"])
        result = calculator.calculate(inp)

        item = PayRunItem(
            pay_run_id=pay_run.id,
            employee_id=emp.id,
            company_id=emp.company_id,
            regular_hours=h.regular_hours,
            overtime_hours=h.overtime_hours,
            regular_pay=float(result.regular_pay),
            overtime_pay=float(result.overtime_pay),
            bonus_pay=float(result.bonus_pay),
            reimbursement=float(result.reimbursement),
            gross_pay=float(result.gross_pay),
            federal_income_tax=float(result.federal_income_tax),
            state_income_tax=float(result.state_income_tax),
            social_security_tax=float(result.social_security_tax),
            medicare_tax=float(result.medicare_tax),
            additional_medicare_tax=float(result.additional_medicare_tax),
            total_employee_taxes=float(result.total_employee_taxes),
            employer_social_security=float(result.employer_social_security),
            employer_medicare=float(result.employer_medicare),
            futa_tax=float(result.futa_tax),
            suta_tax=float(result.suta_tax),
            total_employer_taxes=float(result.total_employer_taxes),
            health_insurance=float(result.health_insurance),
            dental_insurance=float(result.dental_insurance),
            vision_insurance=float(result.vision_insurance),
            retirement_401k=float(result.retirement_401k),
            hsa=float(result.hsa),
            total_pretax_deductions=float(result.total_pretax_deductions),
            garnishment=float(result.garnishment),
            net_pay=float(result.net_pay),
            ytd_gross=ytd["gross"] + float(result.gross_pay),
            ytd_net=ytd["net"] + float(result.net_pay),
            ytd_federal_tax=ytd["federal"] + float(result.federal_income_tax),
            ytd_state_tax=ytd["state"] + float(result.state_income_tax),
            ytd_ss_tax=ytd["social_security"] + float(result.social_security_tax),
            ytd_medicare_tax=ytd["medicare"] + float(result.medicare_tax),
        )
        await item.insert()
        run_items.append(item)

        totals["gross"] += float(result.gross_pay)
        totals["emp_taxes"] += float(result.total_employee_taxes)
        totals["emp_employer_taxes"] += float(result.total_employer_taxes)
        totals["deductions"] += float(result.total_pretax_deductions)
        totals["net"] += float(result.net_pay)

    # Update pay run totals
    pay_run.total_gross = round(totals["gross"], 2)
    pay_run.total_employee_taxes = round(totals["emp_taxes"], 2)
    pay_run.total_employer_taxes = round(totals["emp_employer_taxes"], 2)
    pay_run.total_deductions = round(totals["deductions"], 2)
    pay_run.total_net = round(totals["net"], 2)
    pay_run.employee_count = len(run_items)
    pay_run.status = "completed"
    await pay_run.save()

    for item in run_items:
        stub = Paystub(
            pay_run_item_id=item.id,
            employee_id=item.employee_id,
            company_id=item.company_id,
            pay_run_id=pay_run.id,
        )
        await stub.insert()

    pay_period.status = "completed"
    await pay_period.save()

    # Generate PDFs in background
    background_tasks.add_task(_generate_all_pdfs, str(pay_run.id))

    return {
        "pay_run_id": str(pay_run.id),
        "status": "completed",
        "employee_count": pay_run.employee_count,
        "totals": {
            "gross": float(pay_run.total_gross),
            "employee_taxes": float(pay_run.total_employee_taxes),
            "employer_taxes": float(pay_run.total_employer_taxes),
            "deductions": float(pay_run.total_deductions),
            "net": float(pay_run.total_net),
        },
    }


# ── History ────────────────────────────────────────────────────────
@router.get("/history")
async def payroll_history(
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    runs = await PayRun.find(
        PayRun.company_id == current_user["company_id"]
    ).sort("-created_at").skip(skip).limit(limit).to_list()
    
    total = await PayRun.find(
        PayRun.company_id == current_user["company_id"]
    ).count()

    return {
        "total": total,
        "runs": [_serialize_run(r) for r in runs],
    }


@router.get("/history/{run_id}")
async def get_pay_run(
    run_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    run = await PayRun.find_one(
        PayRun.id == run_id, 
        PayRun.company_id == current_user["company_id"]
    )
    if not run:
        raise HTTPException(404, "Pay run not found")

    items = await PayRunItem.find(PayRunItem.pay_run_id == run_id).to_list()

    return {**_serialize_run(run), "items": [_serialize_item(i) for i in items]}


# ── Calculators ────────────────────────────────────────────────────
class CalcRequest(BaseModel):
    annual_salary: Optional[float] = None
    hourly_rate: Optional[float] = None
    pay_type: str = "salary"
    pay_frequency: str = "biweekly"
    filing_status: str = "single"
    state_code: str = "NY"
    regular_hours: float = 80
    overtime_hours: float = 0
    health_insurance: float = 0
    retirement_401k_pct: float = 0
    bonus_pay: float = 0


@router.post("/calculate")
async def calculate_paycheck(req: CalcRequest):
    pay_rate = req.annual_salary if req.pay_type == "salary" else req.hourly_rate
    if not pay_rate:
        raise HTTPException(400, "Provide annual_salary or hourly_rate")

    inp = PayCalculationInput(
        pay_type=req.pay_type,
        pay_rate=pay_rate,
        filing_status=req.filing_status,
        state_code=req.state_code,
        pay_frequency=req.pay_frequency,
        regular_hours=req.regular_hours,
        overtime_hours=req.overtime_hours,
        health_insurance_deduction=req.health_insurance,
        retirement_401k_pct=req.retirement_401k_pct,
        bonus_pay=req.bonus_pay,
    )
    result = calculator.calculate(inp)

    return {
        "gross_pay": float(result.gross_pay),
        "taxable_gross": float(result.taxable_gross),
        "pretax_deductions": float(result.total_pretax_deductions),
        "federal_income_tax": float(result.federal_income_tax),
        "state_income_tax": float(result.state_income_tax),
        "social_security_tax": float(result.social_security_tax),
        "medicare_tax": float(result.medicare_tax),
        "total_employee_taxes": float(result.total_employee_taxes),
        "net_pay": float(result.net_pay),
        "employer_total": float(result.total_employer_taxes),
        "true_cost": float(result.gross_pay) + float(result.total_employer_taxes),
        "effective_federal_rate": float(result.effective_federal_rate),
        "effective_state_rate": float(result.effective_state_rate),
    }


# ── Helpers ────────────────────────────────────────────────────────
async def _load_employees(company_id, req):
    query = {
        "company_id": company_id if isinstance(company_id, UUID) else UUID(company_id),
        "status": "active"
    }
    if req.employee_ids:
        query["_id"] = {"$in": [UUID(eid) for eid in req.employee_ids]}
    
    employees = await Employee.find(query).to_list()

    hours_map = {}
    if req.hours_overrides:
        for h in req.hours_overrides:
            hours_map[h.employee_id] = h

    return employees, hours_map


async def _resolve_pay_period(company_id, req):
    if req.pay_period_id:
        period = await PayPeriod.get(UUID(req.pay_period_id))
        return period

    period_start = req.period_start or date.today().replace(day=1)
    period_end = req.period_end or date.today()
    pay_date = req.pay_date or (period_end + timedelta(days=5))

    period = PayPeriod(
        company_id=company_id if isinstance(company_id, UUID) else UUID(company_id),
        period_start=period_start,
        period_end=period_end,
        pay_date=pay_date,
        status="processing",
    )
    await period.insert()
    return period


def _build_calc_input(emp: Employee, h: HoursOverride, ytd_gross=0, ytd_ss_wages=0) -> PayCalculationInput:
    return PayCalculationInput(
        pay_type=emp.pay_type,
        pay_rate=float(emp.pay_rate),
        filing_status=emp.filing_status or "single",
        state_code=emp.state_code or "NY",
        pay_frequency=emp.pay_frequency or "biweekly",
        regular_hours=h.regular_hours,
        overtime_hours=h.overtime_hours,
        double_time_hours=h.double_time_hours,
        bonus_pay=h.bonus_pay,
        commission_pay=h.commission_pay,
        reimbursement=h.reimbursement,
        health_insurance_deduction=float(emp.health_insurance_deduction or 0),
        dental_deduction=float(emp.dental_deduction or 0),
        vision_deduction=float(emp.vision_deduction or 0),
        retirement_401k_pct=float(emp.retirement_401k_pct or 0),
        hsa_deduction=float(emp.hsa_deduction or 0),
        garnishment_amount=float(emp.garnishment_amount or 0),
        additional_federal_withholding=float(emp.additional_federal_withholding or 0),
        exempt_from_federal=emp.exempt_from_federal or False,
        exempt_from_state=emp.exempt_from_state or False,
        ytd_gross=ytd_gross,
        ytd_ss_wages=ytd_ss_wages,
    )


async def _get_ytd(employee_id, before_date):
    # Find all completed pay runs for this company and year
    # Aggregation is more efficient for sum
    from beanie.operators import In
    
    # 1. Find relevant pay periods
    periods = await PayPeriod.find(
        PayPeriod.period_start >= date(before_date.year, 1, 1),
        PayPeriod.period_end < before_date,
        PayPeriod.status == "completed"
    ).to_list()
    period_ids = [p.id for p in periods]
    
    if not period_ids:
        return {"gross": 0, "federal": 0, "social_security": 0, "medicare": 0, "net": 0}
        
    # 2. Find completed pay runs for those periods
    runs = await PayRun.find(
        In(PayRun.pay_period_id, period_ids),
        PayRun.status == "completed"
    ).to_list()
    run_ids = [r.id for r in runs]
    
    if not run_ids:
        return {"gross": 0, "federal": 0, "social_security": 0, "medicare": 0, "net": 0}

    # 3. Sum PayRunItems
    pipeline = [
        {"$match": {"employee_id": employee_id, "pay_run_id": {"$in": run_ids}}},
        {"$group": {
            "_id": None,
            "gross": {"$sum": "$gross_pay"},
            "federal": {"$sum": "$federal_income_tax"},
            "state": {"$sum": "$state_income_tax"},
            "social_security": {"$sum": "$social_security_tax"},
            "medicare": {"$sum": "$medicare_tax"},
            "net": {"$sum": "$net_pay"}
        }}
    ]
    
    results = await PayRunItem.aggregate(pipeline).to_list()
    if not results:
        return {"gross": 0, "federal": 0, "social_security": 0, "medicare": 0, "net": 0}
        
    row = results[0]
    return {
        "gross": float(row.get("gross", 0)),
        "federal": float(row.get("federal", 0)),
        "state": float(row.get("state", 0)),
        "social_security": float(row.get("social_security", 0)),
        "medicare": float(row.get("medicare", 0)),
        "net": float(row.get("net", 0)),
    }


async def _generate_all_pdfs(pay_run_id: str):
    """Background task to generate PDFs for all paystubs in a run."""
    from services.background import generate_paystub_pdfs_and_notify
    await generate_paystub_pdfs_and_notify(pay_run_id)


def _result_to_dict(employee_id, emp, result):
    return {
        "employee_id": employee_id,
        "employee_name": f"{emp.first_name} {emp.last_name}",
        "department": emp.department,
        "pay_type": emp.pay_type,
        "gross_pay": float(result.gross_pay),
        "regular_pay": float(result.regular_pay),
        "overtime_pay": float(result.overtime_pay),
        "bonus_pay": float(result.bonus_pay),
        "total_pretax_deductions": float(result.total_pretax_deductions),
        "taxable_gross": float(result.taxable_gross),
        "federal_income_tax": float(result.federal_income_tax),
        "state_income_tax": float(result.state_income_tax),
        "social_security_tax": float(result.social_security_tax),
        "medicare_tax": float(result.medicare_tax),
        "total_employee_taxes": float(result.total_employee_taxes),
        "employer_social_security": float(result.employer_social_security),
        "employer_medicare": float(result.employer_medicare),
        "futa_tax": float(result.futa_tax),
        "total_employer_taxes": float(result.total_employer_taxes),
        "net_pay": float(result.net_pay),
        "effective_federal_rate": float(result.effective_federal_rate),
        "effective_state_rate": float(result.effective_state_rate),
    }


def _serialize_run(r: PayRun) -> dict:
    return {
        "id": str(r.id),
        "pay_period_id": str(r.pay_period_id),
        "status": r.status,
        "total_gross": float(r.total_gross or 0),
        "total_employee_taxes": float(r.total_employee_taxes or 0),
        "total_employer_taxes": float(r.total_employer_taxes or 0),
        "total_deductions": float(r.total_deductions or 0),
        "total_net": float(r.total_net or 0),
        "employee_count": r.employee_count,
        "created_at": str(r.created_at),
        "completed_at": str(getattr(r, 'completed_at', None)) if hasattr(r, 'completed_at') else None,
    }


def _serialize_item(i: PayRunItem) -> dict:
    return {
        "id": str(i.id),
        "employee_id": str(i.employee_id),
        "gross_pay": float(i.gross_pay or 0),
        "total_employee_taxes": float(i.total_employee_taxes or 0),
        "total_pretax_deductions": float(i.total_pretax_deductions or 0),
        "net_pay": float(i.net_pay or 0),
        "federal_income_tax": float(i.federal_income_tax or 0),
        "state_income_tax": float(i.state_income_tax or 0),
        "social_security_tax": float(i.social_security_tax or 0),
        "medicare_tax": float(i.medicare_tax or 0),
    }


async def _fire_payroll_webhook(company_id, run_id, emp_count, gross, net):
    try:
        from routes.webhooks import fire_event
        await fire_event("payroll.run.completed", company_id, {
            "pay_run_id": run_id,
            "employee_count": emp_count,
            "total_gross": gross,
            "total_net": net,
        })
    except Exception:
        pass
