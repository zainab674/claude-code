from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import PayRun, PayRunItem, PayPeriod, Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/ytd-summary")
async def ytd_summary(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Year-to-date totals across all completed pay runs."""
    year = year or date.today().year
    result = await db.execute(
        select(
            func.sum(PayRun.total_gross).label("total_gross"),
            func.sum(PayRun.total_employee_taxes).label("total_employee_taxes"),
            func.sum(PayRun.total_employer_taxes).label("total_employer_taxes"),
            func.sum(PayRun.total_deductions).label("total_deductions"),
            func.sum(PayRun.total_net).label("total_net"),
            func.count(PayRun.id).label("run_count"),
        )
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    row = result.first()
    gross = float(row.total_gross or 0)
    emp_tax = float(row.total_employee_taxes or 0)
    er_tax = float(row.total_employer_taxes or 0)
    return {
        "year": year,
        "run_count": row.run_count or 0,
        "total_gross": gross,
        "total_employee_taxes": emp_tax,
        "total_employer_taxes": er_tax,
        "total_deductions": float(row.total_deductions or 0),
        "total_net": float(row.total_net or 0),
        "true_total_cost": round(gross + er_tax, 2),
        "effective_tax_rate": round((emp_tax / gross * 100) if gross else 0, 2),
    }


@router.get("/by-department")
async def by_department(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Payroll cost breakdown by department."""
    year = year or date.today().year
    result = await db.execute(
        select(
            Employee.department,
            func.count(PayRunItem.employee_id.distinct()).label("headcount"),
            func.sum(PayRunItem.gross_pay).label("gross"),
            func.sum(PayRunItem.total_employee_taxes).label("taxes"),
            func.sum(PayRunItem.total_employer_taxes).label("employer_taxes"),
            func.sum(PayRunItem.net_pay).label("net"),
        )
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .join(Employee, PayRunItem.employee_id == Employee.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
        .group_by(Employee.department)
        .order_by(func.sum(PayRunItem.gross_pay).desc())
    )
    rows = result.all()
    return {
        "year": year,
        "departments": [
            {
                "department": r.department or "Unassigned",
                "headcount": r.headcount,
                "gross": float(r.gross or 0),
                "taxes": float(r.taxes or 0),
                "employer_taxes": float(r.employer_taxes or 0),
                "net": float(r.net or 0),
                "true_cost": float((r.gross or 0) + (r.employer_taxes or 0)),
            }
            for r in rows
        ],
    }


@router.get("/employee-ytd")
async def employee_ytd(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Per-employee YTD totals — for W-2 prep."""
    year = year or date.today().year
    result = await db.execute(
        select(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            Employee.department,
            Employee.job_title,
            Employee.state_code,
            func.sum(PayRunItem.gross_pay).label("gross"),
            func.sum(PayRunItem.federal_income_tax).label("federal_tax"),
            func.sum(PayRunItem.state_income_tax).label("state_tax"),
            func.sum(PayRunItem.social_security_tax).label("ss_tax"),
            func.sum(PayRunItem.medicare_tax).label("medicare_tax"),
            func.sum(PayRunItem.retirement_401k).label("retirement"),
            func.sum(PayRunItem.health_insurance).label("health"),
            func.sum(PayRunItem.net_pay).label("net"),
        )
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .join(Employee, PayRunItem.employee_id == Employee.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
        .group_by(Employee.id, Employee.first_name, Employee.last_name,
                  Employee.department, Employee.job_title, Employee.state_code)
        .order_by(func.sum(PayRunItem.gross_pay).desc())
    )
    rows = result.all()
    return {
        "year": year,
        "employees": [
            {
                "id": str(r.id),
                "name": f"{r.first_name} {r.last_name}",
                "department": r.department,
                "job_title": r.job_title,
                "state": r.state_code,
                "ytd_gross": float(r.gross or 0),
                "ytd_federal_tax": float(r.federal_tax or 0),
                "ytd_state_tax": float(r.state_tax or 0),
                "ytd_social_security": float(r.ss_tax or 0),
                "ytd_medicare": float(r.medicare_tax or 0),
                "ytd_401k": float(r.retirement or 0),
                "ytd_health_ins": float(r.health or 0),
                "ytd_net": float(r.net or 0),
            }
            for r in rows
        ],
    }


@router.get("/tax-liability")
async def tax_liability(
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Tax liability summary — what you owe to IRS / state agencies."""
    year = year or date.today().year
    result = await db.execute(
        select(
            func.sum(PayRunItem.federal_income_tax).label("federal_income"),
            func.sum(PayRunItem.social_security_tax + PayRunItem.employer_social_security).label("total_ss"),
            func.sum(PayRunItem.medicare_tax + PayRunItem.employer_medicare).label("total_medicare"),
            func.sum(PayRunItem.state_income_tax).label("state_income"),
            func.sum(PayRunItem.futa_tax).label("futa"),
            func.sum(PayRunItem.suta_tax).label("suta"),
        )
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRun.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    row = result.first()
    fed_income = float(row.federal_income or 0)
    total_ss = float(row.total_ss or 0)
    total_med = float(row.total_medicare or 0)
    futa = float(row.futa or 0)
    suta = float(row.suta or 0)
    state = float(row.state_income or 0)
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
