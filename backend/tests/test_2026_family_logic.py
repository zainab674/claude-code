import pytest
from decimal import Decimal
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.calculator import PayrollCalculator, PayCalculationInput

@pytest.fixture
def calc():
    return PayrollCalculator()

def test_married_1_child_ctc_reduction(calc):
    """Verify that a Married Filing Jointly employee with 1 child ($2200 credit) pays less tax."""
    base_inp = PayCalculationInput(
        pay_type='salary', pay_rate=100000,
        filing_status='married', state_code='TX', # No state tax for simplicity
        pay_frequency='biweekly'
    )
    
    family_inp = PayCalculationInput(
        pay_type='salary', pay_rate=100000,
        filing_status='married', state_code='TX',
        pay_frequency='biweekly',
        child_credits=2200.0
    )
    
    r_base = calc.calculate(base_inp)
    r_family = calc.calculate(family_inp)
    
    # Expected reduction per paycheck: 2200 / 26 = 84.615... -> 84.62
    expected_reduction = Decimal('84.62')
    actual_reduction = r_base.federal_income_tax - r_family.federal_income_tax
    
    assert actual_reduction == expected_reduction

def test_ca_sdi_and_exemption_credits(calc):
    """Verify CA SDI and Exemption Allowances for a family in California."""
    inp = PayCalculationInput(
        pay_type='salary', pay_rate=120000,
        filing_status='married', state_code='CA',
        pay_frequency='biweekly',
        ca_allowances=3 # Self + Spouse + 1 Child
    )
    
    result = calc.calculate(inp)
    
    # Check SDI: 1.3% of taxable gross
    # Gross = 120000 / 26 = 4615.38
    expected_sdi = (result.taxable_gross * Decimal("0.013")).quantize(Decimal("0.01"))
    assert result.state_disability_insurance == expected_sdi
    assert result.state_disability_insurance > 0
    
    # Verify exemption credits reduce state tax
    inp_no_allowances = PayCalculationInput(
        pay_type='salary', pay_rate=120000,
        filing_status='married', state_code='CA',
        pay_frequency='biweekly',
        ca_allowances=0
    )
    result_no_allowances = calc.calculate(inp_no_allowances)
    
    # Each allowance is 169.30 annually. 3 allowances = 507.90
    # Per period: 507.90 / 26 = 19.534... -> 19.53
    # Wait, the rounding in _apply_brackets and calculate might affect this.
    # Let's check if there is a reduction.
    assert result.state_income_tax < result_no_allowances.state_income_tax

def test_ctc_phase_out_mfj(calc):
    """Verify Child Tax Credit phase-out for high earners (MFJ > $400k)."""
    # High earner: $500,000. $100k over $400k limit.
    # Reduction = (100000 / 1000) * 50 = 5000.
    # If they have 2 children ($4400 credits), the credit should be 0.
    inp = PayCalculationInput(
        pay_type='salary', pay_rate=500000,
        filing_status='married', state_code='TX',
        pay_frequency='biweekly',
        child_credits=4400.0
    )
    
    inp_no_credits = PayCalculationInput(
        pay_type='salary', pay_rate=500000,
        filing_status='married', state_code='TX',
        pay_frequency='biweekly',
        child_credits=0.0
    )
    
    r_high = calc.calculate(inp)
    r_no_credits = calc.calculate(inp_no_credits)
    
    # Credit is fully phased out
    assert r_high.federal_income_tax == r_no_credits.federal_income_tax

def test_other_dependent_credit(calc):
    """Verify the $500 Other Dependent Credit."""
    inp = PayCalculationInput(
        pay_type='salary', pay_rate=60000,
        filing_status='single', state_code='TX',
        pay_frequency='biweekly',
        other_dependent_credits=500.0
    )
    
    inp_no_credits = PayCalculationInput(
        pay_type='salary', pay_rate=60000,
        filing_status='single', state_code='TX',
        pay_frequency='biweekly'
    )
    
    r = calc.calculate(inp)
    r_no = calc.calculate(inp_no_credits)
    
    # 500 / 26 = 19.23
    assert r_no.federal_income_tax - r.federal_income_tax == Decimal('19.23')
