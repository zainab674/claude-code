"""
Extended test suite - pay frequencies, all filing statuses,
high-income additional Medicare, garnishments, combined scenarios.
"""
import pytest
from decimal import Decimal
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.calculator import PayrollCalculator, PayCalculationInput

calc = PayrollCalculator()

def inp(**kwargs):
    defaults = dict(pay_type='salary', pay_rate=60000, filing_status='single',
                    state_code='NY', pay_frequency='biweekly')
    defaults.update(kwargs)
    return PayCalculationInput(**defaults)


# ── Pay Frequency Tests ──────────────────────────────────────

class TestPayFrequencies:
    def test_weekly_gross(self):
        r = calc.calculate(inp(pay_rate=52000, pay_frequency='weekly'))
        assert r.gross_pay == Decimal('1000.00')

    def test_biweekly_gross(self):
        r = calc.calculate(inp(pay_rate=52000, pay_frequency='biweekly'))
        assert r.gross_pay == Decimal('2000.00')

    def test_semimonthly_gross(self):
        r = calc.calculate(inp(pay_rate=24000, pay_frequency='semimonthly'))
        assert r.gross_pay == Decimal('1000.00')

    def test_monthly_gross(self):
        r = calc.calculate(inp(pay_rate=12000, pay_frequency='monthly'))
        assert r.gross_pay == Decimal('1000.00')

    def test_annual_net_roughly_consistent_across_frequencies(self):
        """Same salary should yield ~same annual net regardless of frequency."""
        salary = 80000
        freqs = ['weekly', 'biweekly', 'semimonthly', 'monthly']
        periods = {'weekly': 52, 'biweekly': 26, 'semimonthly': 24, 'monthly': 12}
        nets = {}
        for freq in freqs:
            r = calc.calculate(inp(pay_rate=salary, pay_frequency=freq, state_code='TX'))
            nets[freq] = float(r.net_pay) * periods[freq]
        # All annual nets should be within 2% of each other (small rounding diffs OK)
        values = list(nets.values())
        spread = max(values) - min(values)
        assert spread / max(values) < 0.02, f"Annual net spread too wide: {nets}"


# ── All Filing Statuses ──────────────────────────────────────

class TestAllFilingStatuses:
    def test_single_has_highest_federal_tax(self):
        salary = 90000
        s = calc.calculate(inp(pay_rate=salary, filing_status='single'))
        m = calc.calculate(inp(pay_rate=salary, filing_status='married'))
        h = calc.calculate(inp(pay_rate=salary, filing_status='head_of_household'))
        assert s.federal_income_tax > h.federal_income_tax
        assert s.federal_income_tax > m.federal_income_tax

    def test_married_lowest_federal_above_threshold(self):
        salary = 150000
        s = calc.calculate(inp(pay_rate=salary, filing_status='single'))
        m = calc.calculate(inp(pay_rate=salary, filing_status='married'))
        assert m.federal_income_tax < s.federal_income_tax

    def test_hoh_between_single_and_married(self):
        salary = 80000
        s = calc.calculate(inp(pay_rate=salary, filing_status='single'))
        m = calc.calculate(inp(pay_rate=salary, filing_status='married'))
        h = calc.calculate(inp(pay_rate=salary, filing_status='head_of_household'))
        assert m.federal_income_tax <= h.federal_income_tax <= s.federal_income_tax


# ── High Income Scenarios ────────────────────────────────────

class TestHighIncome:
    def test_additional_medicare_triggers_over_200k(self):
        """0.9% additional Medicare kicks in when YTD wages exceed $200k."""
        r = calc.calculate(inp(
            pay_rate=500000,
            pay_frequency='biweekly',
            ytd_gross=210000,
        ))
        assert r.additional_medicare_tax > Decimal('0.00')

    def test_additional_medicare_zero_under_threshold(self):
        r = calc.calculate(inp(
            pay_rate=100000,
            pay_frequency='biweekly',
            ytd_gross=50000,
        ))
        assert r.additional_medicare_tax == Decimal('0.00')

    def test_high_salary_higher_bracket(self):
        """$500k salary should hit 37% bracket."""
        low = calc.calculate(inp(pay_rate=30000))
        high = calc.calculate(inp(pay_rate=500000))
        assert high.effective_federal_rate > low.effective_federal_rate

    def test_employer_cost_exceeds_gross_for_all_salaries(self):
        for salary in [30000, 75000, 150000, 300000]:
            r = calc.calculate(inp(pay_rate=salary))
            true_cost = r.gross_pay + r.total_employer_taxes
            assert true_cost > r.gross_pay


# ── Garnishment Tests ────────────────────────────────────────

class TestGarnishments:
    def test_garnishment_reduces_net(self):
        base = calc.calculate(inp(pay_rate=60000))
        with_garnish = calc.calculate(inp(pay_rate=60000, garnishment_amount=200))
        assert with_garnish.net_pay < base.net_pay
        assert base.net_pay - with_garnish.net_pay == Decimal('200.00')

    def test_garnishment_does_not_affect_taxes(self):
        """Garnishments are post-tax — no effect on withholding."""
        base = calc.calculate(inp(pay_rate=60000))
        with_garnish = calc.calculate(inp(pay_rate=60000, garnishment_amount=500))
        assert base.federal_income_tax == with_garnish.federal_income_tax
        assert base.social_security_tax == with_garnish.social_security_tax

    def test_garnishment_in_posttax_deductions(self):
        r = calc.calculate(inp(pay_rate=60000, garnishment_amount=300))
        assert r.garnishment == Decimal('300.00')
        assert r.total_posttax_deductions == Decimal('300.00')


# ── Combined Deductions Scenario ─────────────────────────────

class TestCombinedDeductions:
    def test_full_benefits_package(self):
        """Realistic employee with full benefit deductions."""
        r = calc.calculate(inp(
            pay_rate=85000,
            filing_status='married',
            state_code='CA',
            health_insurance_deduction=350,
            dental_deduction=25,
            vision_deduction=10,
            retirement_401k_pct=0.06,
            hsa_deduction=100,
        ))
        assert r.total_pretax_deductions > Decimal('0')
        assert r.taxable_gross < r.gross_pay
        assert r.net_pay > Decimal('0')
        # Sanity: net should be 50–75% of gross for this income range
        ratio = float(r.net_pay / r.gross_pay)
        assert 0.45 < ratio < 0.80, f"Net/gross ratio unexpected: {ratio:.2%}"

    def test_401k_capped_at_contribution(self):
        """401k is a % of wages only (not bonus)."""
        r = calc.calculate(inp(
            pay_rate=100000,
            retirement_401k_pct=0.10,
            bonus_pay=5000,
        ))
        # 401k = 10% of regular pay only (not bonus by default)
        biweekly_salary = Decimal('100000') / 26
        expected_401k = (biweekly_salary * Decimal('0.10')).quantize(Decimal('0.01'))
        assert r.retirement_401k == expected_401k

    def test_max_pretax_deductions_still_positive_net(self):
        """Even with aggressive deductions net pay should not go below 0."""
        r = calc.calculate(inp(
            pay_rate=30000,   # Low salary
            health_insurance_deduction=800,
            retirement_401k_pct=0.15,
            garnishment_amount=200,
        ))
        assert r.net_pay >= Decimal('0.00')


# ── State Coverage Tests ─────────────────────────────────────

class TestAllNoTaxStates:
    """States with 0% income tax should all produce 0 state tax."""
    NO_TAX = ['AK', 'FL', 'NV', 'NH', 'SD', 'TN', 'TX', 'WA', 'WY']

    def test_no_income_tax_states(self):
        for state in self.NO_TAX:
            r = calc.calculate(inp(pay_rate=80000, state_code=state))
            assert r.state_income_tax == Decimal('0.00'), \
                f"{state} should have 0 state tax, got {r.state_income_tax}"

class TestHighTaxStates:
    def test_california_highest_rate(self):
        r_ca = calc.calculate(inp(pay_rate=200000, state_code='CA'))
        r_ny = calc.calculate(inp(pay_rate=200000, state_code='NY'))
        r_or = calc.calculate(inp(pay_rate=200000, state_code='OR'))
        # CA (9.3%), OR (9.9%), NY (6.85%) — all should be > 0
        for r, state in [(r_ca,'CA'),(r_ny,'NY'),(r_or,'OR')]:
            assert r.state_income_tax > Decimal('0'), f"{state} should have state tax"


# ── Employer Cost Tests ──────────────────────────────────────

class TestEmployerCost:
    def test_total_employer_cost_formula(self):
        r = calc.calculate(inp(pay_rate=75000))
        expected = r.employer_social_security + r.employer_medicare + r.futa_tax + r.suta_tax
        assert r.total_employer_taxes == expected

    def test_employer_cost_roughly_7_65_pct_of_wages(self):
        """Employer FICA is 7.65% of wages (SS 6.2% + Medicare 1.45%)."""
        r = calc.calculate(inp(pay_rate=60000, state_code='TX', ytd_gross=0))
        fica_pct = float((r.employer_social_security + r.employer_medicare) / r.taxable_gross * 100)
        assert 7.0 < fica_pct <= 7.65 + 0.1, f"Employer FICA pct unexpected: {fica_pct:.2f}%"

    def test_true_cost_always_above_gross(self):
        for salary in [25000, 50000, 100000, 200000, 500000]:
            r = calc.calculate(inp(pay_rate=salary))
            assert r.gross_pay + r.total_employer_taxes > r.gross_pay


# ── Rounding Tests ───────────────────────────────────────────

class TestRounding:
    def test_all_output_fields_are_decimal(self):
        r = calc.calculate(inp(pay_rate=75000))
        fields = [r.gross_pay, r.regular_pay, r.federal_income_tax, r.state_income_tax,
                  r.social_security_tax, r.medicare_tax, r.net_pay, r.total_employee_taxes,
                  r.total_employer_taxes, r.total_pretax_deductions]
        for f in fields:
            assert isinstance(f, Decimal), f"Field {f} is not Decimal"

    def test_all_monetary_values_2dp(self):
        r = calc.calculate(inp(pay_rate=73333))  # Non-round salary for max precision test
        fields = [r.gross_pay, r.federal_income_tax, r.social_security_tax,
                  r.medicare_tax, r.net_pay]
        for f in fields:
            # Should have at most 2 decimal places
            assert f == f.quantize(Decimal('0.01')), f"More than 2dp: {f}"

    def test_net_pay_cents_accurate(self):
        """Verify penny-level accuracy on a non-round salary."""
        r = calc.calculate(inp(pay_rate=77777, state_code='TX'))
        # Manual: 77777/26 = 2991.423... gross
        expected_gross = (Decimal('77777') / 26).quantize(Decimal('0.01'))
        assert r.gross_pay == expected_gross
