"""
PayrollOS Test Suite
Run: pytest tests/ -v
"""
import pytest
from decimal import Decimal
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.calculator import PayrollCalculator, PayCalculationInput


@pytest.fixture
def calc():
    return PayrollCalculator()


# ── Calculator Tests ────────────────────────────────────────────

class TestSalariedEmployee:
    def test_biweekly_gross(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=78000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        # $78,000 / 26 = $3,000
        assert result.gross_pay == Decimal('3000.00')

    def test_federal_tax_withheld(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=78000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.federal_income_tax > 0

    def test_fica_withheld(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=78000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        # SS = 6.2%, Medicare = 1.45%  of taxable gross
        assert result.social_security_tax > 0
        assert result.medicare_tax > 0

    def test_net_less_than_gross(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.net_pay < result.gross_pay

    def test_married_pays_less_than_single(self, calc):
        base = dict(pay_type='salary', pay_rate=100000, state_code='NY', pay_frequency='biweekly')
        single = calc.calculate(PayCalculationInput(**base, filing_status='single'))
        married = calc.calculate(PayCalculationInput(**base, filing_status='married'))
        assert married.federal_income_tax < single.federal_income_tax

    def test_pretax_deductions_reduce_taxable(self, calc):
        base = PayCalculationInput(
            pay_type='salary', pay_rate=80000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        with_deductions = PayCalculationInput(
            pay_type='salary', pay_rate=80000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            health_insurance_deduction=200,
            retirement_401k_pct=0.05,
        )
        r1 = calc.calculate(base)
        r2 = calc.calculate(with_deductions)
        assert r2.taxable_gross < r1.taxable_gross
        assert r2.federal_income_tax < r1.federal_income_tax


class TestHourlyEmployee:
    def test_regular_pay(self, calc):
        inp = PayCalculationInput(
            pay_type='hourly', pay_rate=25.0,
            filing_status='single', state_code='TX',
            pay_frequency='biweekly',
            regular_hours=80, overtime_hours=0,
        )
        result = calc.calculate(inp)
        assert result.regular_pay == Decimal('2000.00')

    def test_overtime_pay_1_5x(self, calc):
        inp = PayCalculationInput(
            pay_type='hourly', pay_rate=20.0,
            filing_status='single', state_code='TX',
            pay_frequency='biweekly',
            regular_hours=80, overtime_hours=10,
        )
        result = calc.calculate(inp)
        # OT = 10 * 20 * 1.5 = 300
        assert result.overtime_pay == Decimal('300.00')

    def test_gross_includes_overtime(self, calc):
        inp = PayCalculationInput(
            pay_type='hourly', pay_rate=20.0,
            filing_status='single', state_code='TX',
            pay_frequency='biweekly',
            regular_hours=80, overtime_hours=5,
        )
        result = calc.calculate(inp)
        expected = Decimal('1600.00') + Decimal('150.00')
        assert result.gross_pay == expected


class TestStateTax:
    def test_no_state_tax_texas(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=80000,
            filing_status='single', state_code='TX',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.state_income_tax == Decimal('0.00')

    def test_no_state_tax_florida(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=80000,
            filing_status='single', state_code='FL',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.state_income_tax == Decimal('0.00')

    def test_ny_state_tax_positive(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=80000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.state_income_tax > Decimal('0.00')

    def test_ca_higher_than_ny(self, calc):
        base = dict(pay_type='salary', pay_rate=120000, filing_status='single', pay_frequency='biweekly')
        ny = calc.calculate(PayCalculationInput(**base, state_code='NY'))
        ca = calc.calculate(PayCalculationInput(**base, state_code='CA'))
        assert ca.state_income_tax > ny.state_income_tax


class TestFICAWageBase:
    def test_ss_caps_at_wage_base(self, calc):
        """Employee who has already hit SS wage base pays $0 SS."""
        # SS wage base = $168,600 × 6.2% = $10,453.20 max
        # Pass ytd_gross >= wage_base so ss_remaining = 0
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=300000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            ytd_ss_wages=168600.0,  # 168600 * 0.062
            ytd_gross=200000,              # Well past $168,600 base
        )
        result = calc.calculate(inp)
        assert result.social_security_tax == Decimal('0.00')

    def test_medicare_no_cap(self, calc):
        """Medicare has no wage base cap."""
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=300000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            ytd_gross=250000,
            ytd_ss_wages=168600.0,
        )
        result = calc.calculate(inp)
        assert result.medicare_tax > Decimal('0.00')


class TestBonus:
    def test_bonus_increases_gross(self, calc):
        base = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        with_bonus = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            bonus_pay=5000,
        )
        r1 = calc.calculate(base)
        r2 = calc.calculate(with_bonus)
        assert r2.gross_pay == r1.gross_pay + Decimal('5000')

    def test_reimbursement_not_taxed(self, calc):
        base = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        with_reimb = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            reimbursement=500,
        )
        r1 = calc.calculate(base)
        r2 = calc.calculate(with_reimb)
        # Reimbursement adds to gross but NOT to taxable
        assert r2.gross_pay > r1.gross_pay
        assert r2.taxable_gross == r1.taxable_gross
        assert r2.federal_income_tax == r1.federal_income_tax


class TestExemptions:
    def test_exempt_from_federal(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            exempt_from_federal=True,
        )
        result = calc.calculate(inp)
        assert result.federal_income_tax == Decimal('0.00')

    def test_exempt_from_state(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            exempt_from_state=True,
        )
        result = calc.calculate(inp)
        assert result.state_income_tax == Decimal('0.00')


class TestEmployerTaxes:
    def test_employer_ss_matches_employee(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.employer_social_security == result.social_security_tax

    def test_employer_medicare_matches_employee(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
        )
        result = calc.calculate(inp)
        assert result.employer_medicare == result.medicare_tax

    def test_futa_applies_within_wage_base(self, calc):
        inp = PayCalculationInput(
            pay_type='hourly', pay_rate=15.0,
            filing_status='single', state_code='TX',
            pay_frequency='biweekly',
            regular_hours=80,
            ytd_gross=0,
        )
        result = calc.calculate(inp)
        assert result.futa_tax > Decimal('0.00')

    def test_futa_zero_beyond_wage_base(self, calc):
        inp = PayCalculationInput(
            pay_type='hourly', pay_rate=15.0,
            filing_status='single', state_code='TX',
            pay_frequency='biweekly',
            regular_hours=80,
            ytd_gross=7000,  # Already at FUTA cap
        )
        result = calc.calculate(inp)
        assert result.futa_tax == Decimal('0.00')


class TestNetPay:
    def test_net_pay_formula(self, calc):
        inp = PayCalculationInput(
            pay_type='salary', pay_rate=60000,
            filing_status='single', state_code='NY',
            pay_frequency='biweekly',
            health_insurance_deduction=150,
        )
        result = calc.calculate(inp)
        expected = (result.taxable_gross + result.reimbursement
                    - result.total_employee_taxes
                    - result.total_posttax_deductions)
        assert abs(result.net_pay - expected) < Decimal('0.01')

    def test_net_pay_never_negative(self, calc):
        inp = PayCalculationInput(
            pay_type='hourly', pay_rate=7.25,
            filing_status='single', state_code='CA',
            pay_frequency='biweekly',
            regular_hours=20,
            health_insurance_deduction=1000,  # Extreme deduction
        )
        result = calc.calculate(inp)
        assert result.net_pay >= Decimal('0.00')
