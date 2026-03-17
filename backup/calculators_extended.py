"""
Extended calculator routes — missing from original build.

POST /calculator/net-to-gross      reverse paycheck (target net → required gross)
POST /calculator/funding           payroll funding amount needed before run
POST /calculator/multi-state       employee living in one state, working in another
POST /calculator/pricing           price your payroll service to customers
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.calculator import PayrollCalculator, PayCalculationInput

router = APIRouter(prefix="/calculator", tags=["calculators"])
_calc = PayrollCalculator()


# ── Schemas ────────────────────────────────────────────────────
class NetToGrossRequest(BaseModel):
    target_net: float
    filing_status: str = "single"
    state_code: str = "NY"
    pay_frequency: str = "biweekly"
    health_insurance_deduction: float = 0
    retirement_401k_pct: float = 0
    garnishment_amount: float = 0
    max_iterations: int = 50    # Newton–Raphson safety limit


class FundingRequest(BaseModel):
    pay_run_preview_items: list   # [{employee_id, gross_pay, net_pay, employee_taxes, employer_taxes}]
    payroll_fee_per_employee: float = 0
    ach_fee_per_employee: float = 0.25
    wire_fee: float = 0
    buffer_pct: float = 2.0     # % safety buffer above minimum


class MultiStateRequest(BaseModel):
    annual_salary: float
    work_state: str
    residence_state: str
    pay_frequency: str = "biweekly"
    filing_status: str = "single"
    health_insurance_deduction: float = 0
    retirement_401k_pct: float = 0


class PricingRequest(BaseModel):
    employee_count: int
    payroll_frequency: str = "biweekly"   # weekly|biweekly|semimonthly|monthly
    ach_cost_per_transaction: float = 0.25
    monthly_platform_cost: float = 20.0   # hosting, DB, etc.
    filing_cost_per_quarter: float = 0    # CPA/filing service
    support_hours_per_month: float = 2.0
    support_hourly_rate: float = 50.0
    desired_margin_pct: float = 40.0      # % margin


# ── Frequency helpers ──────────────────────────────────────────
FREQ_PERIODS = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}


# ── Net-to-gross (Newton–Raphson iteration) ────────────────────
@router.post("/net-to-gross")
async def net_to_gross(body: NetToGrossRequest):
    """
    Find the gross pay that produces exactly the requested net pay.
    Uses iterative Newton–Raphson: converges in ~5-8 iterations.
    """
    if body.target_net <= 0:
        raise HTTPException(400, "target_net must be positive")

    target = Decimal(str(body.target_net))
    gross_estimate = target * Decimal("1.35")   # initial guess: net * 1.35

    freq_divisor = FREQ_PERIODS.get(body.pay_frequency, 26)

    for i in range(body.max_iterations):
        inp = PayCalculationInput(
            pay_type="salary",
            pay_rate=float(gross_estimate) * freq_divisor,  # annualise
            pay_frequency=body.pay_frequency,
            filing_status=body.filing_status,
            state_code=body.state_code,
            health_insurance_deduction=body.health_insurance_deduction,
            retirement_401k_pct=body.retirement_401k_pct,
            garnishment_amount=body.garnishment_amount,
        )
        result = _calc.calculate(inp)
        current_net = result.net_pay
        error = current_net - target

        if abs(error) < Decimal("0.01"):
            break

        # Derivative approximation: ∂net/∂gross ≈ (1 - effective_tax_rate)
        effective_rate = Decimal("1") - (current_net / result.gross_pay) if result.gross_pay > 0 else Decimal("0.65")
        delta = error / effective_rate if effective_rate > 0 else error
        gross_estimate -= delta

        if gross_estimate <= 0:
            gross_estimate = target

    final_inp = PayCalculationInput(
        pay_type="salary",
        pay_rate=float(gross_estimate) * freq_divisor,
        pay_frequency=body.pay_frequency,
        filing_status=body.filing_status,
        state_code=body.state_code,
        health_insurance_deduction=body.health_insurance_deduction,
        retirement_401k_pct=body.retirement_401k_pct,
        garnishment_amount=body.garnishment_amount,
    )
    final = _calc.calculate(final_inp)

    return {
        "target_net": float(target),
        "required_gross": round(float(gross_estimate), 2),
        "actual_net": round(float(final.net_pay), 2),
        "difference_cents": round(float(abs(final.net_pay - target) * 100), 1),
        "federal_income_tax": round(float(final.federal_income_tax), 2),
        "state_income_tax": round(float(final.state_income_tax), 2),
        "social_security": round(float(final.social_security_tax), 2),
        "medicare": round(float(final.medicare_tax), 2),
        "pretax_deductions": round(float(final.total_pretax_deductions), 2),
        "effective_gross_up_pct": round(
            (float(gross_estimate) - float(target)) / float(target) * 100, 1
        ),
        "iterations": i + 1,
    }


# ── Payroll funding calculator ─────────────────────────────────
@router.post("/funding")
async def payroll_funding(body: FundingRequest):
    """
    Calculate exactly how much must be in the company bank account
    before approving a payroll run — including taxes, fees, and buffer.
    """
    items = body.pay_run_preview_items

    total_net       = sum(float(i.get("net_pay", 0))        for i in items)
    total_emp_tax   = sum(float(i.get("employee_taxes", 0)) for i in items)
    total_er_tax    = sum(float(i.get("employer_taxes", 0)) for i in items)
    total_gross     = sum(float(i.get("gross_pay", 0))      for i in items)
    n               = len(items)

    ach_fees        = n * body.ach_fee_per_employee
    payroll_fees    = n * body.payroll_fee_per_employee
    wire_fee        = body.wire_fee
    total_fees      = ach_fees + payroll_fees + wire_fee

    # Tax liability breakdown
    # IRS 941 deposit = federal income withheld + both sides of FICA
    # We approximate from the totals
    # Employer FICA ≈ 7.65% of gross
    er_fica         = total_gross * 0.0765
    estimated_941   = total_emp_tax + er_fica

    subtotal        = total_net + estimated_941 + total_fees
    buffer          = subtotal * (body.buffer_pct / 100)
    total_needed    = subtotal + buffer

    return {
        "employee_count": n,
        "breakdown": {
            "net_wages_to_employees":    round(total_net, 2),
            "employee_taxes_withheld":   round(total_emp_tax, 2),
            "employer_fica_liability":   round(er_fica, 2),
            "estimated_irs_941_deposit": round(estimated_941, 2),
            "ach_fees":                  round(ach_fees, 2),
            "payroll_service_fees":      round(payroll_fees, 2),
            "wire_fee":                  round(wire_fee, 2),
            "safety_buffer":             round(buffer, 2),
        },
        "minimum_required": round(subtotal, 2),
        "recommended_with_buffer": round(total_needed, 2),
        "buffer_pct": body.buffer_pct,
        "note": (
            "Deposit IRS 941 taxes via EFTPS by the next banking day after payroll. "
            "Most banks require ACH submission 1-2 business days before pay date."
        ),
    }


# ── Multi-state withholding ────────────────────────────────────
@router.post("/multi-state")
async def multi_state_withholding(body: MultiStateRequest):
    """
    Calculate withholding for an employee who works in one state but
    lives (and pays taxes) in another.

    Rules:
    - Federal tax: always based on federal brackets (same regardless of state)
    - Work state: may have reciprocity agreement with residence state
    - Residence state: typically where the employee files their return
    - Most states tax residents on ALL income; many have reciprocity agreements

    NOTE: This is an estimate. Always verify with a CPA for cross-border employees.
    """
    freq = body.pay_frequency

    # Calculate for work state
    work_inp = PayCalculationInput(
        pay_type="salary", pay_rate=body.annual_salary,
        pay_frequency=freq, filing_status=body.filing_status,
        state_code=body.work_state,
        health_insurance_deduction=body.health_insurance_deduction,
        retirement_401k_pct=body.retirement_401k_pct,
    )
    work_result = _calc.calculate(work_inp)

    # Calculate for residence state
    res_inp = PayCalculationInput(
        pay_type="salary", pay_rate=body.annual_salary,
        pay_frequency=freq, filing_status=body.filing_status,
        state_code=body.residence_state,
        health_insurance_deduction=body.health_insurance_deduction,
        retirement_401k_pct=body.retirement_401k_pct,
    )
    res_result = _calc.calculate(res_inp)

    # Reciprocity check (common pairs)
    RECIPROCITY = {
        frozenset(["NJ","PA"]), frozenset(["MD","DC"]), frozenset(["MD","VA"]),
        frozenset(["DC","VA"]), frozenset(["OH","KY"]), frozenset(["OH","MI"]),
        frozenset(["OH","PA"]), frozenset(["OH","IN"]), frozenset(["OH","WV"]),
        frozenset(["WI","IL"]), frozenset(["WI","IN"]), frozenset(["WI","KY"]),
        frozenset(["WI","MI"]), frozenset(["MN","ND"]), frozenset(["MN","MI"]),
        frozenset(["DC","MD"]),
    }
    has_reciprocity = frozenset([body.work_state, body.residence_state]) in RECIPROCITY

    # No-income-tax states
    NO_TAX_STATES = {"TX","FL","WA","NV","WY","SD","AK","TN","NH"}

    work_no_tax = body.work_state in NO_TAX_STATES
    res_no_tax  = body.residence_state in NO_TAX_STATES

    if has_reciprocity:
        # With reciprocity: only withhold for residence state
        withhold_work_state = 0.0
        withhold_res_state  = float(res_result.state_income_tax)
        rule = "Reciprocity agreement — withhold ONLY for residence state"
    elif work_no_tax and not res_no_tax:
        withhold_work_state = 0.0
        withhold_res_state  = float(res_result.state_income_tax)
        rule = "Work state has no income tax — withhold only for residence state"
    elif res_no_tax and not work_no_tax:
        withhold_work_state = float(work_result.state_income_tax)
        withhold_res_state  = 0.0
        rule = "Residence state has no income tax — withhold only for work state"
    elif work_no_tax and res_no_tax:
        withhold_work_state = 0.0
        withhold_res_state  = 0.0
        rule = "Both states have no income tax — no state withholding required"
    else:
        # General rule: withhold for work state; employee may owe difference to residence state
        withhold_work_state = float(work_result.state_income_tax)
        withhold_res_state  = max(0.0, float(res_result.state_income_tax) - float(work_result.state_income_tax))
        rule = "No reciprocity — withhold for work state + additional for residence state if higher"

    total_state = withhold_work_state + withhold_res_state
    net_pay = float(work_result.gross_pay) - float(work_result.federal_income_tax) - \
              total_state - float(work_result.social_security_tax) - \
              float(work_result.medicare_tax) - float(work_result.total_pretax_deductions)

    return {
        "work_state": body.work_state,
        "residence_state": body.residence_state,
        "has_reciprocity": has_reciprocity,
        "rule_applied": rule,
        "per_paycheck": {
            "gross_pay": round(float(work_result.gross_pay), 2),
            "federal_income_tax": round(float(work_result.federal_income_tax), 2),
            "social_security": round(float(work_result.social_security_tax), 2),
            "medicare": round(float(work_result.medicare_tax), 2),
            "work_state_withholding": round(withhold_work_state, 2),
            "residence_state_withholding": round(withhold_res_state, 2),
            "total_state_withholding": round(total_state, 2),
            "net_pay": round(net_pay, 2),
        },
        "comparison": {
            "work_state_only_net": round(float(work_result.net_pay), 2),
            "residence_state_only_net": round(float(res_result.net_pay), 2),
        },
        "disclaimer": (
            "This is an estimate. Actual withholding depends on reciprocity certificates "
            "filed by the employee (Form IT-2104 in NY, W-4 equivalent). Consult a CPA "
            "for employees working across state lines."
        ),
    }


# ── Payroll service pricing ────────────────────────────────────
@router.post("/pricing")
async def payroll_pricing(body: PricingRequest):
    """
    Calculate how to price your payroll service to customers.
    Covers your costs + desired margin.
    """
    runs_per_month = {
        "weekly": 4.33, "biweekly": 2.17, "semimonthly": 2.0, "monthly": 1.0
    }.get(body.payroll_frequency, 2.17)

    # Per-month costs
    ach_cost_monthly     = body.employee_count * body.ach_cost_per_transaction * runs_per_month
    platform_cost        = body.monthly_platform_cost
    filing_cost_monthly  = body.filing_cost_per_quarter / 3
    support_cost_monthly = body.support_hours_per_month * body.support_hourly_rate

    total_monthly_cost   = ach_cost_monthly + platform_cost + filing_cost_monthly + support_cost_monthly
    cost_per_employee    = total_monthly_cost / max(body.employee_count, 1)

    # Apply margin
    margin_factor = 1 / (1 - body.desired_margin_pct / 100)
    price_per_employee = cost_per_employee * margin_factor
    total_monthly_price = price_per_employee * body.employee_count

    # Common market benchmarks
    gusto_cost     = body.employee_count * 6 + 40   # ~$6/emp + $40 base
    adp_cost       = body.employee_count * 9 + 59   # ~$9/emp + $59 base

    return {
        "employee_count": body.employee_count,
        "payroll_frequency": body.payroll_frequency,
        "runs_per_month": round(runs_per_month, 2),
        "monthly_costs": {
            "ach_fees":         round(ach_cost_monthly, 2),
            "platform":         round(platform_cost, 2),
            "tax_filing":       round(filing_cost_monthly, 2),
            "support":          round(support_cost_monthly, 2),
            "total":            round(total_monthly_cost, 2),
        },
        "pricing": {
            "cost_per_employee_per_month": round(cost_per_employee, 2),
            "price_per_employee_per_month": round(price_per_employee, 2),
            "total_monthly_revenue": round(total_monthly_price, 2),
            "total_monthly_profit": round(total_monthly_price - total_monthly_cost, 2),
            "actual_margin_pct": round(body.desired_margin_pct, 1),
        },
        "market_comparison": {
            "your_price_per_employee": round(price_per_employee, 2),
            "gusto_estimated_monthly": round(gusto_cost, 2),
            "adp_estimated_monthly": round(adp_cost, 2),
            "vs_gusto": f"${round(gusto_cost - total_monthly_price, 2):+,.2f}/mo vs Gusto",
        },
        "suggested_tiers": [
            {"name": "Starter",  "employees": "1–10",  "price": f"${round(price_per_employee * 1.3, 2)}/emp/mo"},
            {"name": "Growth",   "employees": "11–50", "price": f"${round(price_per_employee, 2)}/emp/mo"},
            {"name": "Business", "employees": "51+",   "price": f"${round(price_per_employee * 0.85, 2)}/emp/mo"},
        ],
    }
