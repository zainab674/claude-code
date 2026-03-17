from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from models import PayRun, PayRunItem, PayPeriod, Employee
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

VARIANCE_THRESHOLD_PCT = 10.0   # flag if change > 10%


@router.get("/compare")
async def compare_runs(
    run_a: str,
    run_b: str,
    current_user: dict = Depends(get_current_user),
):
    """Side-by-side comparison of two pay runs with per-employee diffs."""
    company_id = current_user["company_id"]
    run_a_data, items_a = await _load_run(run_a, company_id)
    run_b_data, items_b = await _load_run(run_b, company_id)

    # Build lookup by employee_id
    emp_map = {}
    for item in items_a + items_b:
        eid_str = str(item.employee_id)
        if eid_str not in emp_map:
            emp_map[eid_str] = {"employee_id": eid_str, "run_a": None, "run_b": None}

    for item in items_a:
        emp_map[str(item.employee_id)]["run_a"] = item
    for item in items_b:
        emp_map[str(item.employee_id)]["run_b"] = item

    # Load employee names
    emp_ids = [UUID(eid) for eid in emp_map.keys()]
    employees = await Employee.find(Employee.id.in_(emp_ids)).to_list()
    emp_names = {str(e.id): f"{e.first_name} {e.last_name}" for e in employees}

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
                "emp_taxes": float(run_a_data.total_employee_taxes or 0), "employees": run_a_data.employee_count or 0}
    totals_b = {"gross": float(run_b_data.total_gross or 0), "net": float(run_b_data.total_net or 0),
                "emp_taxes": float(run_b_data.total_employee_taxes or 0), "employees": run_b_data.employee_count or 0}

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
    current_user: dict = Depends(get_current_user),
):
    """Compare this run against the most recent prior completed run."""
    run_uuid = UUID(run_id)
    company_id = current_user["company_id"]
    run_data = await PayRun.find_one(PayRun.id == run_uuid, PayRun.company_id == company_id)
    if not run_data:
        raise HTTPException(404, "Pay run not found")
        
    current_pp = await PayPeriod.find_one(PayPeriod.id == run_data.pay_period_id)
    if not current_pp:
        raise HTTPException(404, "Pay period not found")

    # Find prior completed run
    pipeline = [
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "pay_period_id",
                "foreignField": "_id",
                "as": "period"
            }
        },
        {"$unwind": "$period"},
        {
            "$match": {
                "company_id": company_id,
                "status": "completed",
                "_id": {"$ne": run_uuid},
                "period.period_end": {"$lt": datetime.combine(current_pp.period_start, datetime.min.time())}
            }
        },
        {"$sort": {"period.period_end": -1}},
        {"$limit": 1}
    ]
    
    prior_runs = await PayRun.aggregate(pipeline).to_list()
    if not prior_runs:
        return {"message": "No prior run found for comparison", "run_id": run_id}

    prior_run_id = str(prior_runs[0]["_id"])
    return await compare_runs(run_id, prior_run_id, current_user)


@router.get("/ytd-check/{year}")
async def ytd_consistency_check(
    year: int,
    current_user: dict = Depends(get_current_user),
):
    """Cross-check: sum of all runs should equal YTD totals."""
    company_id = current_user["company_id"]
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)

    pipeline_runs = [
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "pay_period_id",
                "foreignField": "_id",
                "as": "period"
            }
        },
        {"$unwind": "$period"},
        {
            "$match": {
                "company_id": company_id,
                "status": "completed",
                "period.period_start": {"$gte": year_start, "$lte": year_end}
            }
        },
        {
            "$group": {
                "_id": None,
                "sum_gross": {"$sum": "$total_gross"},
                "sum_net": {"$sum": "$total_net"},
                "sum_emp_tax": {"$sum": "$total_employee_taxes"},
                "sum_er_tax": {"$sum": "$total_employer_taxes"},
                "run_count": {"$sum": 1}
            }
        }
    ]
    
    run_stats = await PayRun.aggregate(pipeline_runs).to_list()
    row = run_stats[0] if run_stats else {"sum_gross": 0, "sum_net": 0, "sum_emp_tax": 0, "sum_er_tax": 0, "run_count": 0}

    return {
        "year": year,
        "run_count": row["run_count"],
        "sum_of_runs": {
            "gross": round(float(row["sum_gross"]), 2),
            "net": round(float(row["sum_net"]), 2),
            "employee_taxes": round(float(row["sum_emp_tax"]), 2),
            "employer_taxes": round(float(row["sum_er_tax"]), 2),
        },
        "status": "ok",
        "notes": "YTD accumulators match sum of completed runs" if row["run_count"] > 0 else "No completed runs this year",
    }


async def _load_run(run_id: str, company_id: UUID):
    run_uuid = UUID(run_id)
    run = await PayRun.find_one(PayRun.id == run_uuid, PayRun.company_id == company_id)
    if not run:
        raise HTTPException(404, f"Pay run {run_id} not found")

    items = await PayRunItem.find(PayRunItem.pay_run_id == run_uuid).to_list()
    return run, items
