from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends
from models import PayRun, PayRunItem, PayPeriod, Employee
from utils.auth import get_current_user
from uuid import UUID
from utils.numbers import to_float

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/ytd-summary")
async def ytd_summary(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Year-to-date totals across all completed pay runs."""
    year = year or date.today().year
    company_id = current_user["company_id"]
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)

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
                "period.period_start": {"$gte": year_start, "$lte": year_end}
            }
        },
        {
            "$group": {
                "_id": None,
                "total_gross": {"$sum": "$total_gross"},
                "total_employee_taxes": {"$sum": "$total_employee_taxes"},
                "total_employer_taxes": {"$sum": "$total_employer_taxes"},
                "total_deductions": {"$sum": "$total_deductions"},
                "total_net": {"$sum": "$total_net"},
                "run_count": {"$sum": 1}
            }
        }
    ]
    
    stats = await PayRun.aggregate(pipeline).to_list()
    row = stats[0] if stats else {"total_gross": 0, "total_employee_taxes": 0, "total_employer_taxes": 0, "total_deductions": 0, "total_net": 0, "run_count": 0}

    gross = to_float(row["total_gross"])
    emp_tax = to_float(row["total_employee_taxes"])
    er_tax = to_float(row["total_employer_taxes"])
    
    return {
        "year": year,
        "run_count": row["run_count"],
        "total_gross": gross,
        "total_employee_taxes": emp_tax,
        "total_employer_taxes": er_tax,
        "total_deductions": to_float(row["total_deductions"]),
        "total_net": to_float(row["total_net"]),
        "true_total_cost": round(gross + er_tax, 2),
        "effective_tax_rate": round((emp_tax / gross * 100) if gross else 0, 2),
    }


@router.get("/by-department")
async def by_department(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Payroll cost breakdown by department."""
    year = year or date.today().year
    company_id = current_user["company_id"]
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)

    pipeline = [
        {
            "$lookup": {
                "from": "pay_runs",
                "localField": "pay_run_id",
                "foreignField": "_id",
                "as": "run"
            }
        },
        {"$unwind": "$run"},
        {"$match": {"run.company_id": company_id, "run.status": "completed"}},
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "run.pay_period_id",
                "foreignField": "_id",
                "as": "period"
            }
        },
        {"$unwind": "$period"},
        {"$match": {"period.period_start": {"$gte": year_start, "$lte": year_end}}},
        {
            "$lookup": {
                "from": "employees",
                "localField": "employee_id",
                "foreignField": "_id",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$group": {
                "_id": "$employee.department",
                "headcount": {"$addToSet": "$employee_id"},
                "gross": {"$sum": "$gross_pay"},
                "taxes": {"$sum": "$total_employee_taxes"},
                "employer_taxes": {"$sum": "$total_employer_taxes"},
                "net": {"$sum": "$net_pay"},
            }
        },
        {"$sort": {"gross": -1}}
    ]

    dept_stats = await PayRunItem.aggregate(pipeline).to_list()
    
    return {
        "year": year,
        "departments": [
            {
                "department": r["_id"] or "Unassigned",
                "headcount": len(r["headcount"]),
                "gross": to_float(r["gross"]),
                "taxes": to_float(r["taxes"]),
                "employer_taxes": to_float(r["employer_taxes"]),
                "net": to_float(r["net"]),
                "true_cost": round(to_float(r["gross"]) + to_float(r["employer_taxes"]), 2),
            }
            for r in dept_stats
        ],
    }


@router.get("/employee-ytd")
async def employee_ytd(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Per-employee YTD totals — for W-2 prep."""
    year = year or date.today().year
    company_id = current_user["company_id"]
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)

    pipeline = [
        {
            "$lookup": {
                "from": "pay_runs",
                "localField": "pay_run_id",
                "foreignField": "_id",
                "as": "run"
            }
        },
        {"$unwind": "$run"},
        {"$match": {"run.company_id": company_id, "run.status": "completed"}},
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "run.pay_period_id",
                "foreignField": "_id",
                "as": "period"
            }
        },
        {"$unwind": "$period"},
        {"$match": {"period.period_start": {"$gte": year_start, "$lte": year_end}}},
        {
            "$group": {
                "_id": "$employee_id",
                "gross": {"$sum": "$gross_pay"},
                "federal_tax": {"$sum": "$federal_income_tax"},
                "state_tax": {"$sum": "$state_income_tax"},
                "ss_tax": {"$sum": "$social_security_tax"},
                "medicare_tax": {"$sum": "$medicare_tax"},
                "retirement": {"$sum": "$retirement_401k"},
                "health": {"$sum": "$health_insurance"},
                "net": {"$sum": "$net_pay"},
            }
        },
        {"$sort": {"gross": -1}}
    ]

    ytd_stats = await PayRunItem.aggregate(pipeline).to_list()
    
    employees_ytd = []
    for r in ytd_stats:
        emp = await Employee.find_one(Employee.id == r["_id"])
        if not emp:
            continue
            
        employees_ytd.append({
            "id": str(emp.id),
            "name": f"{emp.first_name} {emp.last_name}",
            "department": emp.department,
            "job_title": emp.job_title,
            "state": emp.state_code,
            "ytd_gross": to_float(r["gross"]),
            "ytd_federal_tax": to_float(r["federal_tax"]),
            "ytd_state_tax": to_float(r["state_tax"]),
            "ytd_social_security": to_float(r["ss_tax"]),
            "ytd_medicare": to_float(r["medicare_tax"]),
            "ytd_401k": to_float(r["retirement"]),
            "ytd_health_ins": to_float(r["health"]),
            "ytd_net": to_float(r["net"]),
        })

    return {
        "year": year,
        "employees": employees_ytd,
    }


@router.get("/tax-liability")
async def tax_liability(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """Tax liability summary — what you owe to IRS / state agencies."""
    year = year or date.today().year
    company_id = current_user["company_id"]
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)

    pipeline = [
        {
            "$lookup": {
                "from": "pay_runs",
                "localField": "pay_run_id",
                "foreignField": "_id",
                "as": "run"
            }
        },
        {"$unwind": "$run"},
        {"$match": {"run.company_id": company_id, "run.status": "completed"}},
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "run.pay_period_id",
                "foreignField": "_id",
                "as": "period"
            }
        },
        {"$unwind": "$period"},
        {"$match": {"period.period_start": {"$gte": year_start, "$lte": year_end}}},
        {
            "$group": {
                "_id": None,
                "federal_income": {"$sum": "$federal_income_tax"},
                "total_ss": {"$sum": {"$add": ["$social_security_tax", "$employer_social_security"]}},
                "total_medicare": {"$sum": {"$add": ["$medicare_tax", "$employer_medicare"]}},
                "state_income": {"$sum": "$state_income_tax"},
                "futa": {"$sum": "$futa_tax"},
                "suta": {"$sum": "$suta_tax"},
            }
        }
    ]

    stats = await PayRunItem.aggregate(pipeline).to_list()
    row = stats[0] if stats else {"federal_income": 0, "total_ss": 0, "total_medicare": 0, "state_income": 0, "futa": 0, "suta": 0}

    fed_income = to_float(row["federal_income"])
    total_ss = to_float(row["total_ss"])
    total_med = to_float(row["total_medicare"])
    futa = to_float(row["futa"])
    suta = to_float(row["suta"])
    state = to_float(row["state_income"])

    return {
        "year": year,
        "irs_941_liability": {
            "federal_income_tax_withheld": fed_income,
            "employee_ss": total_ss / 2,
            "employer_ss": total_ss / 2,
            "employee_medicare": total_med / 2,
            "employer_medicare": total_med / 2,
            "total_941_deposit": round(fed_income + total_ss + total_med, 2),
        },
        "irs_940_futa": round(futa, 2),
        "state_income_tax_withheld": round(state, 2),
        "suta": round(suta, 2),
        "total_tax_liability": round(fed_income + total_ss + total_med + futa + suta + state, 2),
    }
