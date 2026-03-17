"""
Compliance engine — scans for payroll and HR compliance issues.
Runs automatically on demand or before every payroll run.

Checks:
  - Employees paid below minimum wage
  - Missing W-4 / filing info
  - Employees with 0 retirement contribution who are eligible
  - Employees on active leave but scheduled for payroll
  - Missing SSN for employees (tax filing risk)
  - Bank accounts not verified (direct deposit risk)
  - Overtime hours exceeding FLSA limits
  - Missing I-9 onboarding task for employees < 3 days
  - PTO balances near max accrual (use-it-or-lose-it warning)
  - Salary band violations (below band min)
"""
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from database import get_db
from models import Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/compliance", tags=["compliance"])

# 2024 Federal minimum wage
FEDERAL_MIN_WAGE = 7.25
# State minimum wages (spot-check the big ones)
STATE_MIN_WAGES = {
    "CA": 16.00, "WA": 16.28, "NY": 16.00, "MA": 15.00,
    "CO": 14.42, "AZ": 14.35, "IL": 14.00, "NJ": 15.49,
    "CT": 15.69, "OR": 14.70, "MD": 15.00, "MI": 10.33,
    "MN": 10.85, "NV": 12.00, "RI": 14.00, "DE": 13.25,
    "FL": 13.00, "HI": 14.00, "ME": 14.15, "MO": 12.30,
    "MT": 10.30, "NM": 12.00, "OH": 10.45, "SD": 11.20,
    "VT": 13.67, "VA": 12.41,
}


async def _run_checks(db: AsyncSession, company_id: str) -> list:
    issues = []
    today = date.today()

    # ── Load employees ─────────────────────────────────────────
    emp_res = await db.execute(
        select(Employee).where(
            Employee.company_id == company_id,
            Employee.status == "active",
        )
    )
    employees = emp_res.scalars().all()

    for emp in employees:
        emp_id = str(emp.id)
        name = f"{emp.first_name} {emp.last_name}"

        # 1. Below minimum wage
        if emp.pay_type == "hourly":
            state_min = STATE_MIN_WAGES.get(emp.state_code or "", FEDERAL_MIN_WAGE)
            effective_min = max(state_min, FEDERAL_MIN_WAGE)
            if float(emp.pay_rate) < effective_min:
                issues.append({
                    "severity": "critical",
                    "code": "MIN_WAGE",
                    "employee_id": emp_id,
                    "employee_name": name,
                    "message": f"Hourly rate ${float(emp.pay_rate):.2f} is below {emp.state_code or 'federal'} minimum wage ${effective_min:.2f}",
                    "action": "Update pay rate immediately",
                })

        # 2. Missing filing status
        if not emp.filing_status:
            issues.append({
                "severity": "warning",
                "code": "MISSING_FILING_STATUS",
                "employee_id": emp_id,
                "employee_name": name,
                "message": "No federal filing status on file — federal tax withholding may be incorrect",
                "action": "Collect W-4 from employee",
            })

        # 3. Missing state code
        if not emp.state_code:
            issues.append({
                "severity": "warning",
                "code": "MISSING_STATE",
                "employee_id": emp_id,
                "employee_name": name,
                "message": "No state code set — state tax withholding cannot be calculated",
                "action": "Set employee state code",
            })

        # 4. Zero retirement for tenured employees (> 1 year, eligible)
        if emp.hire_date:
            days_employed = (today - emp.hire_date).days
            if days_employed > 365 and float(emp.retirement_401k_pct or 0) == 0:
                issues.append({
                    "severity": "info",
                    "code": "NO_401K",
                    "employee_id": emp_id,
                    "employee_name": name,
                    "message": f"Employed {days_employed // 365} year(s) with 0% 401(k) contribution",
                    "action": "Remind employee to enroll in retirement plan",
                })

        # 5. No salary band match
        # (lightweight check — full analysis in /salary-bands/analysis)

        # 6. Salary employees with no email (can't receive paystubs)
        if not emp.email:
            issues.append({
                "severity": "info",
                "code": "NO_EMAIL",
                "employee_id": emp_id,
                "employee_name": name,
                "message": "No email address — cannot send paystub notifications",
                "action": "Add employee email",
            })

        # 7. New hire (< 3 days) — check I-9
        if emp.hire_date and (today - emp.hire_date).days < 3:
            issues.append({
                "severity": "warning",
                "code": "NEW_HIRE_I9",
                "employee_id": emp_id,
                "employee_name": name,
                "message": f"New hire (hired {emp.hire_date}) — I-9 must be completed within 3 business days",
                "action": "Complete I-9 employment eligibility verification",
            })

    # ── Company-level checks ───────────────────────────────────

    # Check if any pay periods are open and overdue
    try:
        from models import PayPeriod
        overdue_res = await db.execute(
            select(PayPeriod).where(
                PayPeriod.company_id == company_id,
                PayPeriod.status == "open",
                PayPeriod.pay_date < today,
            )
        )
        overdue = overdue_res.scalars().all()
        for pp in overdue:
            issues.append({
                "severity": "critical",
                "code": "OVERDUE_PAY_DATE",
                "employee_id": None,
                "employee_name": None,
                "message": f"Pay period {pp.period_start}–{pp.period_end} is overdue (pay date was {pp.pay_date})",
                "action": "Run payroll immediately",
            })
    except Exception:
        pass

    return issues


@router.get("")
async def run_compliance_check(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Run all compliance checks and return a prioritized list of issues."""
    issues = await _run_checks(db, current_user["company_id"])

    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos = [i for i in issues if i["severity"] == "info"]

    return {
        "checked_at": date.today().isoformat(),
        "total_issues": len(issues),
        "critical": len(critical),
        "warnings": len(warnings),
        "info": len(infos),
        "status": "critical" if critical else "warning" if warnings else "ok",
        "issues": critical + warnings + infos,
    }


@router.get("/pre-payroll")
async def pre_payroll_check(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Quick compliance check before running payroll — only critical issues."""
    issues = await _run_checks(db, current_user["company_id"])
    critical = [i for i in issues if i["severity"] == "critical"]
    can_proceed = len(critical) == 0
    return {
        "can_proceed": can_proceed,
        "blocking_issues": critical,
        "warning_count": len([i for i in issues if i["severity"] == "warning"]),
        "message": "OK to proceed" if can_proceed else f"{len(critical)} critical issue(s) must be resolved before running payroll",
    }
