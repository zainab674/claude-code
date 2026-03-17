"""
Payroll reconciliation — compare pay runs and detect discrepancies.

Useful for:
  - Comparing this period vs last period (variance analysis)
  - Detecting employees whose pay changed unexpectedly
  - Audit trail for accountants
  - Year-over-year comparison

GET /reconciliation/compare?run_a={id}&run_b={id}
GET /reconciliation/variance/{run_id}   vs previous run
GET /reconciliation/ytd-check/{year}    cross-check YTD against sum of runs
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import PayRun, PayRunItem, PayPeriod, Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

VARIANCE_THRESHOLD_PCT = 10.0   # flag if change > 10%


@router.get("/compare")
async def compare_runs(
    run_a: str,
    run_b: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Side-by-side comparison of two pay runs with per-employee diffs."""
    run_a_data, items_a = await _load_run(db, run_a, current_user["company_id"])
    run_b_data, items_b = await _load_run(db, run_b, current_user["company_id"])

    # Build lookup by employee_id
    emp_map = {}
    for item in items_a + items_b:
        eid = str(item.employee_id)
        if eid not in emp_map:
            emp_map[eid] = {"employee_id": eid, "run_a": None, "run_b": None}

    for item in items_a:
        emp_map[str(item.employee_id)]["run_a"] = item
    for item in items_b:
        emp_map[str(item.employee_id)]["run_b"] = item

    # Load employee names
    emp_names = {}
    if emp_map:
        emp_res = await db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name)
            .where(Employee.id.in_(emp_map.keys()))
        )
        for row in emp_res.all():
            emp_names[str(row.id)] = f"{row.first_name} {row.last_name}"

    diffs = []
    flags = 0
    for eid, data in emp_map.items():
        a = data["run_a"]
        b = data["run_b"]
        gross_a = float(a.gross_pay or 0) if a else 0
        gross_b = float(b.gross_pay or 0) if b else 0
        net_a   = float(a.net_pay or 0) if a else 0
        net_b   = float(b.net_pay or 0) if b else 0

        gross_diff = gross_b - gross_a
        net_diff   = net_b - net_a
        gross_pct  = (gross_diff / gross_a * 100) if gross_a else None
        net_pct    = (net_diff / net_a * 100) if net_a else None

        flag = (
            (a is None and b is not None) or
            (a is not None and b is None) or
            (gross_pct is not None and abs(gross_pct) > VARIANCE_THRESHOLD_PCT)
        )
        if flag:
            flags += 1

        diffs.append({
            "employee_id": eid,
            "employee_name": emp_names.get(eid, "Unknown"),
            "only_in_a": b is None and a is not None,
            "only_in_b": a is None and b is not None,
            "gross_a": gross_a, "gross_b": gross_b,
            "gross_diff": round(gross_diff, 2),
            "gross_pct_change": round(gross_pct, 1) if gross_pct is not None else None,
            "net_a": net_a, "net_b": net_b,
            "net_diff": round(net_diff, 2),
            "flagged": flag,
        })

    totals_a = {"gross": float(run_a_data.total_gross or 0), "net": float(run_a_data.total_net or 0),
                "emp_taxes": float(run_a_data.total_employee_taxes or 0), "employees": run_a_data.employee_count}
    totals_b = {"gross": float(run_b_data.total_gross or 0), "net": float(run_b_data.total_net or 0),
                "emp_taxes": float(run_b_data.total_employee_taxes or 0), "employees": run_b_data.employee_count}

    return {
        "run_a_id": run_a, "run_b_id": run_b,
        "totals_a": totals_a, "totals_b": totals_b,
        "total_diff": {k: round(totals_b[k] - totals_a[k], 2) for k in totals_a},
        "flagged_employees": flags,
        "threshold_pct": VARIANCE_THRESHOLD_PCT,
        "employees": sorted(diffs, key=lambda x: abs(x["gross_diff"]), reverse=True),
    }


@router.get("/variance/{run_id}")
async def variance_vs_prior(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Compare this run against the most recent prior completed run."""
    run_data, _ = await _load_run(db, run_id, current_user["company_id"])
    pp_res = await db.execute(select(PayPeriod).where(PayPeriod.id == run_data.pay_period_id))
    current_pp = pp_res.scalar_one_or_none()

    if not current_pp:
        raise HTTPException(404, "Pay period not found")

    prior_run_res = await db.execute(
        select(PayRun)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            PayPeriod.period_end < current_pp.period_start,
            PayRun.id != run_id,
        )
        .order_by(PayPeriod.period_end.desc())
        .limit(1)
    )
    prior = prior_run_res.scalar_one_or_none()

    if not prior:
        return {"message": "No prior run found for comparison", "run_id": run_id}

    return await compare_runs(run_id, str(prior.id), db, current_user)


@router.get("/ytd-check/{year}")
async def ytd_consistency_check(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Cross-check: sum of all runs should equal YTD totals."""
    runs_res = await db.execute(
        select(
            func.sum(PayRun.total_gross).label("sum_gross"),
            func.sum(PayRun.total_net).label("sum_net"),
            func.sum(PayRun.total_employee_taxes).label("sum_emp_tax"),
            func.sum(PayRun.total_employer_taxes).label("sum_er_tax"),
            func.count(PayRun.id).label("run_count"),
        )
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    row = runs_res.first()

    # Cross-check against YTD accumulators in pay_run_items
    items_res = await db.execute(
        select(
            func.max(PayRunItem.ytd_gross).label("max_ytd_gross"),
            func.max(PayRunItem.ytd_net).label("max_ytd_net"),
        )
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRunItem.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    ytd_row = items_res.first()

    gross_sum = float(row.sum_gross or 0)
    net_sum   = float(row.sum_net or 0)

    return {
        "year": year,
        "run_count": row.run_count or 0,
        "sum_of_runs": {
            "gross": round(gross_sum, 2),
            "net": round(net_sum, 2),
            "employee_taxes": round(float(row.sum_emp_tax or 0), 2),
            "employer_taxes": round(float(row.sum_er_tax or 0), 2),
        },
        "status": "ok",
        "notes": "YTD accumulators match sum of completed runs" if row.run_count > 0 else "No completed runs this year",
    }


async def _load_run(db, run_id, company_id):
    run_res = await db.execute(
        select(PayRun).where(PayRun.id == run_id, PayRun.company_id == company_id)
    )
    run = run_res.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Pay run {run_id} not found")

    items_res = await db.execute(
        select(PayRunItem).where(PayRunItem.pay_run_id == run_id)
    )
    items = items_res.scalars().all()
    return run, items
