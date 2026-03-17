from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends
from models import Employee, PayPeriod
from utils.auth import get_current_user
from uuid import UUID

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


async def _run_checks(company_id: UUID) -> list:
    issues = []
    today = date.today()

    # ── Load employees ─────────────────────────────────────────
    employees = await Employee.find(
        Employee.company_id == company_id,
        Employee.status == "active",
    ).to_list()

    for emp in employees:
        emp_id = str(emp.id)
        name = f"{emp.first_name} {emp.last_name}"

        # 1. Below minimum wage
        if emp.pay_type == "hourly":
            state_min = STATE_MIN_WAGES.get(emp.state_code or "", FEDERAL_MIN_WAGE)
            effective_min = max(state_min, FEDERAL_MIN_WAGE)
            if float(emp.pay_rate or 0) < effective_min:
                issues.append({
                    "severity": "critical",
                    "code": "MIN_WAGE",
                    "employee_id": emp_id,
                    "employee_name": name,
                    "message": f"Hourly rate ${float(emp.pay_rate or 0):.2f} is below {emp.state_code or 'federal'} minimum wage ${effective_min:.2f}",
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

        # 4. Zero retirement for tenured employees (> 1 year)
        if emp.hire_date:
            hire_dt = datetime.combine(emp.hire_date, datetime.min.time()) if isinstance(emp.hire_date, date) else emp.hire_date
            days_employed = (datetime.utcnow() - hire_dt).days
            if days_employed > 365 and float(emp.retirement_401k_pct or 0) == 0:
                issues.append({
                    "severity": "info",
                    "code": "NO_401K",
                    "employee_id": emp_id,
                    "employee_name": name,
                    "message": f"Employed {days_employed // 365} year(s) with 0% 401(k) contribution",
                    "action": "Remind employee to enroll in retirement plan",
                })

        # 5. No salary employees with no email
        if not emp.email:
            issues.append({
                "severity": "info",
                "code": "NO_EMAIL",
                "employee_id": emp_id,
                "employee_name": name,
                "message": "No email address — cannot send paystub notifications",
                "action": "Add employee email",
            })

        # 6. New hire (< 3 days) — check I-9
        if emp.hire_date:
            hire_dt = datetime.combine(emp.hire_date, datetime.min.time()) if isinstance(emp.hire_date, date) else emp.hire_date
            if (datetime.utcnow() - hire_dt).days < 3:
                issues.append({
                    "severity": "warning",
                    "code": "NEW_HIRE_I9",
                    "employee_id": emp_id,
                    "employee_name": name,
                    "message": f"New hire (hired {emp.hire_date}) — I-9 must be completed within 3 business days",
                    "action": "Complete I-9 employment eligibility verification",
                })

    # ── Company-level checks ───────────────────────────────────
    overdue_periods = await PayPeriod.find(
        PayPeriod.company_id == company_id,
        PayPeriod.status == "open",
        PayPeriod.pay_date < today,
    ).to_list()
    
    for pp in overdue_periods:
        issues.append({
            "severity": "critical",
            "code": "OVERDUE_PAY_DATE",
            "employee_id": None,
            "employee_name": None,
            "message": f"Pay period {pp.period_start}–{pp.period_end} is overdue (pay date was {pp.pay_date})",
            "action": "Run payroll immediately",
        })

    return issues


@router.get("")
async def run_compliance_check(
    current_user: dict = Depends(get_current_user),
):
    """Run all compliance checks and return a prioritized list of issues."""
    issues = await _run_checks(current_user["company_id"])

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
    current_user: dict = Depends(get_current_user),
):
    """Quick compliance check before running payroll — only critical issues."""
    issues = await _run_checks(current_user["company_id"])
    critical = [i for i in issues if i["severity"] == "critical"]
    can_proceed = len(critical) == 0
    return {
        "can_proceed": can_proceed,
        "blocking_issues": critical,
        "warning_count": len([i for i in issues if i["severity"] == "warning"]),
        "message": "OK to proceed" if can_proceed else f"{len(critical)} critical issue(s) must be resolved before running payroll",
    }
