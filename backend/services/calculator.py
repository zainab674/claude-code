"""
Payroll Calculation Engine
All tax calculations are estimates based on 2024 IRS tables.
Do NOT use for actual payroll without a licensed payroll provider.
"""
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional


# ── 2026 Federal Tax Brackets ───────────────────────────────
FEDERAL_BRACKETS = {
    "single": [
        (12400,  0.10),
        (50400,  0.12),
        (105700, 0.22),
        (201775, 0.24),
        (256225, 0.32),
        (640600, 0.35),
        (float("inf"), 0.37),
    ],
    "married": [
        (24800,  0.10),
        (100800, 0.12),
        (211400, 0.22),
        (403550, 0.24),
        (512450, 0.32),
        (768700, 0.35),
        (float("inf"), 0.37),
    ],
    "head_of_household": [
        (17700,  0.10),
        (67450,  0.12),
        (105700, 0.22),
        (201750, 0.24),
        (256200, 0.32),
        (640600, 0.35),
        (float("inf"), 0.37),
    ],
}

# ── 2026 State Tax Brackets ───────────────────────────────
STATE_BRACKETS = {
    "NY": {
        "single": [
            (12800, 0.040),
            (17650, 0.045),
            (20900, 0.0525),
            (107650, 0.055),
            (269300, 0.060),
            (1616450, 0.0685),
            (5000000, 0.0965),
            (25000000, 0.103),
            (float("inf"), 0.109),
        ],
        "married": [
            (17150, 0.040),
            (23600, 0.045),
            (27900, 0.0525),
            (161550, 0.055),
            (323200, 0.060),
            (2155350, 0.0685),
            (5000000, 0.0965),
            (25000000, 0.103),
            (float("inf"), 0.109),
        ],
        "head_of_household": [
            (8500, 0.040),
            (11700, 0.045),
            (13900, 0.0525),
            (80650, 0.055),
            (215400, 0.060),
            (1077550, 0.0685),
            (5000000, 0.0965),
            (25000000, 0.103),
            (float("inf"), 0.109),
        ]
    },
    "CA": {
        "single": [
            (11079, 0.01),
            (26264, 0.02),
            (41452, 0.04),
            (57542, 0.06),
            (72724, 0.08),
            (371479, 0.093),
            (445771, 0.103),
            (557215, 0.113),
            (float("inf"), 0.123),
        ],
        "married": [
            (22158, 0.01),
            (52528, 0.02),
            (82904, 0.04),
            (115084, 0.06),
            (145448, 0.08),
            (742958, 0.093),
            (891542, 0.103),
            (1114430, 0.113),
            (float("inf"), 0.123),
        ],
        "head_of_household": [
            (22173, 0.01),
            (52530, 0.02),
            (67716, 0.04),
            (83805, 0.06),
            (98990, 0.08),
            (505208, 0.093),
            (606251, 0.103),
            (757816, 0.113),
            (float("inf"), 0.123),
        ]
    }
}

CA_SDI_RATE = Decimal("0.013")  # 1.3% for 2026
CA_EXEMPTION_ALLOWANCE = Decimal("169.30")

# State income tax rates (flat rate approximations)
STATE_TAX_RATES = {
    "AL": 0.050, "AK": 0.000, "AZ": 0.025, "AR": 0.055,
    "CA": 0.093, "CO": 0.044, "CT": 0.069, "DE": 0.066,
    "FL": 0.000, "GA": 0.055, "HI": 0.080, "ID": 0.058,
    "IL": 0.0495,"IN": 0.030, "IA": 0.060, "KS": 0.057,
    "KY": 0.045, "LA": 0.042, "ME": 0.075, "MD": 0.060,
    "MA": 0.050, "MI": 0.0425,"MN": 0.070, "MS": 0.050,
    "MO": 0.054, "MT": 0.069, "NE": 0.068, "NV": 0.000,
    "NH": 0.000, "NJ": 0.064, "NM": 0.059, "NY": 0.0685,
    "NC": 0.0525,"ND": 0.025, "OH": 0.040, "OK": 0.050,
    "OR": 0.099, "PA": 0.0307,"RI": 0.059, "SC": 0.070,
    "SD": 0.000, "TN": 0.000, "TX": 0.000, "UT": 0.045,
    "VT": 0.066, "VA": 0.058, "WA": 0.000, "WV": 0.065,
    "WI": 0.075, "WY": 0.000,
}

# FICA constants
SOCIAL_SECURITY_RATE = Decimal("0.062")      # employee
MEDICARE_RATE = Decimal("0.0145")            # employee
ADDITIONAL_MEDICARE_RATE = Decimal("0.009")  # over $200k
SS_WAGE_BASE = Decimal("184500")             # 2026 SS wage base
MEDICARE_THRESHOLD = Decimal("200000")

# Employer-side
EMPLOYER_SS_RATE = Decimal("0.062")
EMPLOYER_MEDICARE_RATE = Decimal("0.0145")
FUTA_RATE = Decimal("0.006")
FUTA_WAGE_BASE = Decimal("7000")

# Standard deduction (2026)
STANDARD_DEDUCTION = {
    "single": Decimal("16100"),
    "married": Decimal("32200"),
    "head_of_household": Decimal("24150"),
}
ADDITIONAL_STD_DEDUCTION = {
    "single": Decimal("2050"),
    "married": Decimal("1650"),
    "head_of_household": Decimal("2050"),
}
# Senior Bonus Deduction (OBBBA)
SENIOR_BONUS_AMOUNT = Decimal("6000")
SENIOR_BONUS_PHASE_OUT = {
    "single": (75000, 175000),
    "married": (150000, 250000),
    "head_of_household": (75000, 175000),
}


@dataclass
class PayCalculationInput:
    # Employee info
    pay_type: str           # "salary" | "hourly"
    pay_rate: float         # annual salary or hourly rate
    filing_status: str      # "single" | "married" | "head_of_household"
    state_code: str         # e.g. "NY"
    pay_frequency: str      # "weekly" | "biweekly" | "semimonthly" | "monthly"

    # Hours (for hourly; salaried defaults computed)
    regular_hours: float = 80.0   # per period
    overtime_hours: float = 0.0
    double_time_hours: float = 0.0
    pto_hours: float = 0.0
    sick_hours: float = 0.0

    # Extras
    bonus_pay: float = 0.0
    commission_pay: float = 0.0
    tips_pay: float = 0.0
    reimbursement: float = 0.0    # non-taxable

    # Pre-tax deductions
    health_insurance_deduction: float = 0.0
    dental_deduction: float = 0.0
    vision_deduction: float = 0.0
    retirement_401k_pct: float = 0.0
    hsa_deduction: float = 0.0
    additional_federal_withholding: float = 0.0

    # Post-tax
    garnishment_amount: float = 0.0

    # Flags
    exempt_from_federal: bool = False
    exempt_from_state: bool = False
    is_65_plus: bool = False
    is_blind: bool = False

    # 2026 Dependents & Credits
    child_credits: float = 0.0          # Annual total (e.g. 2200 per child)
    other_dependent_credits: float = 0.0 # Annual total (e.g. 500)
    dependent_care_credits: float = 0.0  # Annual total
    ca_allowances: int = 0              # For CA exemption credits

    # YTD (for wage base caps)
    # ytd_gross    = total YTD gross wages (FUTA cap + Medicare threshold)
    # ytd_ss_wages = total YTD SS-taxable wages paid (tracks $168,600 SS wage base)
    ytd_gross: float = 0.0
    ytd_ss_wages: float = 0.0   # YTD SS-subject wages (NOT the tax dollar amount)


@dataclass
class PayCalculationResult:
    # Earnings
    regular_pay: Decimal
    overtime_pay: Decimal
    double_time_pay: Decimal
    bonus_pay: Decimal
    commission_pay: Decimal
    reimbursement: Decimal
    tips_pay: Decimal
    gross_pay: Decimal                # all taxable + non-taxable

    # Pre-tax deductions
    health_insurance: Decimal
    dental_insurance: Decimal
    vision_insurance: Decimal
    retirement_401k: Decimal
    hsa: Decimal
    total_pretax_deductions: Decimal

    taxable_gross: Decimal            # gross minus pre-tax deductions

    # Employee taxes
    federal_income_tax: Decimal
    state_income_tax: Decimal
    state_disability_insurance: Decimal  # e.g. CA SDI
    local_income_tax: Decimal
    social_security_tax: Decimal
    medicare_tax: Decimal
    additional_medicare_tax: Decimal
    total_employee_taxes: Decimal

    # Employer taxes
    employer_social_security: Decimal
    employer_medicare: Decimal
    futa_tax: Decimal
    suta_tax: Decimal
    total_employer_taxes: Decimal

    # Post-tax
    garnishment: Decimal
    total_posttax_deductions: Decimal

    net_pay: Decimal

    # Effective rates for reference
    effective_federal_rate: Decimal
    effective_state_rate: Decimal


class PayrollCalculator:
    PERIODS_PER_YEAR = {"weekly": 52, "biweekly": 26, "semimonthly": 24, "monthly": 12}

    def calculate(self, inp: PayCalculationInput) -> PayCalculationResult:
        p = self.PERIODS_PER_YEAR.get(inp.pay_frequency, 26)
        rate = Decimal(str(inp.pay_rate))

        # ── Earnings ───────────────────────────────────────────
        if inp.pay_type == "salary":
            regular_pay = rate / p
            overtime_pay = Decimal("0")
            double_pay = Decimal("0")
            hourly_equiv = rate / 52 / 40
        else:
            hourly_equiv = rate
            regular_pay = rate * Decimal(str(inp.regular_hours))
            overtime_pay = rate * Decimal("1.5") * Decimal(str(inp.overtime_hours))
            double_pay = rate * Decimal("2.0") * Decimal(str(inp.double_time_hours))

        bonus = Decimal(str(inp.bonus_pay))
        commission = Decimal(str(inp.commission_pay))
        tips = Decimal(str(inp.tips_pay))
        reimbursement = Decimal(str(inp.reimbursement))

        gross_pay = regular_pay + overtime_pay + double_pay + bonus + commission + tips + reimbursement

        # ── Pre-tax deductions (reduce federal/state taxable) ──
        health = Decimal(str(inp.health_insurance_deduction))
        dental = Decimal(str(inp.dental_deduction))
        vision = Decimal(str(inp.vision_deduction))
        retirement = (regular_pay + overtime_pay + double_pay) * Decimal(str(inp.retirement_401k_pct))
        hsa = Decimal(str(inp.hsa_deduction))
        total_pretax = health + dental + vision + retirement + hsa

        taxable_gross = gross_pay - reimbursement - total_pretax
        if taxable_gross < 0:
            taxable_gross = Decimal("0")

        # ── Federal Income Tax (annualize → apply bracket → de-annualize) ──
        if inp.exempt_from_federal:
            fed_tax = Decimal("0")
        else:
            annual_taxable = taxable_gross * p
            
            std_ded = STANDARD_DEDUCTION.get(inp.filing_status, STANDARD_DEDUCTION["single"])
            
            # Additional deduction for 65+ or blind
            extra_ded = Decimal("0")
            if inp.is_65_plus:
                extra_ded += ADDITIONAL_STD_DEDUCTION.get(inp.filing_status, ADDITIONAL_STD_DEDUCTION["single"])
            if inp.is_blind:
                extra_ded += ADDITIONAL_STD_DEDUCTION.get(inp.filing_status, ADDITIONAL_STD_DEDUCTION["single"])
            
            # Senior Bonus Deduction (OBBBA)
            senior_bonus = Decimal("0")
            if inp.is_65_plus:
                magi = annual_taxable  # Approximation
                threshold_start, threshold_end = SENIOR_BONUS_PHASE_OUT.get(inp.filing_status, SENIOR_BONUS_PHASE_OUT["single"])
                if magi <= threshold_start:
                    senior_bonus = SENIOR_BONUS_AMOUNT
                elif magi < threshold_end:
                    excess = magi - threshold_start
                    reduction = (excess / 1000) * 60
                    senior_bonus = max(SENIOR_BONUS_AMOUNT - Decimal(str(reduction)), Decimal("0"))
                else:
                    senior_bonus = Decimal("0")
            
            taxable_income = max(annual_taxable - std_ded - extra_ded - senior_bonus, Decimal("0"))
            annual_fed = self._apply_brackets(taxable_income, FEDERAL_BRACKETS.get(inp.filing_status, FEDERAL_BRACKETS["single"]))
            
            # --- 2026 Child Tax Credit & Other Credits ---
            # Phase-out: Starts at $400,000 for MFJ. $50 reduction per $1,000 over.
            phase_out_start = 400000 if inp.filing_status == "married" else 200000
            total_annual_credits = Decimal(str(inp.child_credits)) + Decimal(str(inp.other_dependent_credits))
            
            if annual_taxable > phase_out_start:
                excess = annual_taxable - Decimal(str(phase_out_start))
                reduction = (excess // 1000) * 50
                total_annual_credits = max(total_annual_credits - Decimal(str(reduction)), Decimal("0"))
            
            net_annual_fed = max(annual_fed - total_annual_credits, Decimal("0"))
            fed_tax = (net_annual_fed / p).quantize(Decimal("0.01"))
            fed_tax += Decimal(str(inp.additional_federal_withholding))

        # ── FICA ──────────────────────────────────────────────
        ytd_gross = Decimal(str(inp.ytd_gross))
        ytd_ss_wages = Decimal(str(inp.ytd_ss_wages))  # wages already taxed for SS

        # Social Security — wage base is $168,600 in wages (not tax dollars)
        ss_remaining = max(SS_WAGE_BASE - ytd_ss_wages, Decimal("0"))
        ss_taxable = min(taxable_gross, ss_remaining)
        ss_tax = (ss_taxable * SOCIAL_SECURITY_RATE).quantize(Decimal("0.01"))

        # Medicare (no wage base cap)
        medicare_tax = (taxable_gross * MEDICARE_RATE).quantize(Decimal("0.01"))

        # Additional Medicare (over $200k annual)
        add_medicare = Decimal("0")
        annual_gross_approx = ytd_gross + taxable_gross
        if annual_gross_approx > MEDICARE_THRESHOLD:
            excess = annual_gross_approx - max(ytd_gross, MEDICARE_THRESHOLD)
            if excess > 0:
                add_medicare = (excess * ADDITIONAL_MEDICARE_RATE).quantize(Decimal("0.01"))

        total_employee_taxes = fed_tax + ss_tax + medicare_tax + add_medicare

        # ── State Disability Insurance (CA SDI) ──────────────────
        state_disability_insurance = Decimal("0")
        if inp.state_code == "CA":
            state_disability_insurance = (taxable_gross * CA_SDI_RATE).quantize(Decimal("0.01"))
        
        total_employee_taxes += state_disability_insurance

        # ── State Income Tax ──────────────────────────────────
        if inp.exempt_from_state:
            state_tax = Decimal("0")
        else:
            state_brackets = STATE_BRACKETS.get(inp.state_code)
            if state_brackets:
                annual_taxable = taxable_gross * p
                brackets = state_brackets.get(inp.filing_status, state_brackets["single"])
                annual_state_tax = self._apply_brackets(annual_taxable, brackets)
                
                # CA Mental Health Tax (1% > $1M)
                if inp.state_code == "CA" and annual_taxable > 1000000:
                    annual_state_tax += (annual_taxable - 1000000) * Decimal("0.01")
                
                # CA Exemption Credits
                if inp.state_code == "CA" and inp.ca_allowances > 0:
                    ca_credits = Decimal(str(inp.ca_allowances)) * CA_EXEMPTION_ALLOWANCE
                    annual_state_tax = max(annual_state_tax - ca_credits, Decimal("0"))
                
                state_tax = (annual_state_tax / p).quantize(Decimal("0.01"))
            else:
                state_rate = Decimal(str(STATE_TAX_RATES.get(inp.state_code, 0.05)))
                state_tax = (taxable_gross * state_rate).quantize(Decimal("0.01"))

        local_tax = Decimal("0")
        total_employee_taxes += state_tax + local_tax

        # ── Employer Taxes ────────────────────────────────────
        emp_ss_taxable = min(taxable_gross, max(SS_WAGE_BASE - ytd_ss_wages, Decimal("0")))
        emp_ss = (emp_ss_taxable * EMPLOYER_SS_RATE).quantize(Decimal("0.01"))
        emp_medicare = (taxable_gross * EMPLOYER_MEDICARE_RATE).quantize(Decimal("0.01"))

        # FUTA ($7k wage base, 0.6%)
        futa_remaining = max(FUTA_WAGE_BASE - ytd_gross, Decimal("0"))
        futa_taxable = min(taxable_gross, futa_remaining)
        futa = (futa_taxable * FUTA_RATE).quantize(Decimal("0.01"))

        suta = Decimal("0")  # varies by state/employer history
        total_employer_taxes = emp_ss + emp_medicare + futa + suta

        # ── Post-tax deductions ───────────────────────────────
        garnishment = Decimal(str(inp.garnishment_amount))
        total_posttax = garnishment

        # ── Net Pay ───────────────────────────────────────────
        net_pay = taxable_gross + reimbursement - total_employee_taxes - total_posttax
        net_pay = max(net_pay, Decimal("0"))

        eff_fed = (fed_tax / taxable_gross * 100).quantize(Decimal("0.01")) if taxable_gross else Decimal("0")
        eff_state = (state_tax / taxable_gross * 100).quantize(Decimal("0.01")) if taxable_gross else Decimal("0")

        return PayCalculationResult(
            regular_pay=regular_pay.quantize(Decimal("0.01")),
            overtime_pay=overtime_pay.quantize(Decimal("0.01")),
            double_time_pay=double_pay.quantize(Decimal("0.01")),
            bonus_pay=bonus,
            commission_pay=commission,
            reimbursement=reimbursement,
            tips_pay=tips,
            gross_pay=gross_pay.quantize(Decimal("0.01")),
            health_insurance=health,
            dental_insurance=dental,
            vision_insurance=vision,
            retirement_401k=retirement.quantize(Decimal("0.01")),
            hsa=hsa,
            total_pretax_deductions=total_pretax.quantize(Decimal("0.01")),
            taxable_gross=taxable_gross,
            federal_income_tax=fed_tax,
            state_income_tax=state_tax,
            state_disability_insurance=state_disability_insurance,
            local_income_tax=local_tax,
            social_security_tax=ss_tax,
            medicare_tax=medicare_tax,
            additional_medicare_tax=add_medicare,
            total_employee_taxes=total_employee_taxes.quantize(Decimal("0.01")),
            employer_social_security=emp_ss,
            employer_medicare=emp_medicare,
            futa_tax=futa,
            suta_tax=suta,
            total_employer_taxes=total_employer_taxes.quantize(Decimal("0.01")),
            garnishment=garnishment,
            total_posttax_deductions=total_posttax,
            net_pay=net_pay.quantize(Decimal("0.01")),
            effective_federal_rate=eff_fed,
            effective_state_rate=eff_state,
        )

    def _apply_brackets(self, taxable_income: Decimal, brackets: list) -> Decimal:
        tax = Decimal("0")
        prev_limit = Decimal("0")
        for limit, rate in brackets:
            lim = Decimal(str(limit))
            if taxable_income <= prev_limit:
                break
            portion = min(taxable_income, lim) - prev_limit
            tax += portion * Decimal(str(rate))
            prev_limit = lim
        return tax.quantize(Decimal("0.01"))


# Singleton
calculator = PayrollCalculator()
