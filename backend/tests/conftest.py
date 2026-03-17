"""
pytest configuration and shared fixtures
Run: pytest tests/ -v
"""
import pytest
import sys
import os

# Ensure backend root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Calculator fixture ───────────────────────────────────────
@pytest.fixture(scope="session")
def calc():
    from services.calculator import PayrollCalculator
    return PayrollCalculator()


@pytest.fixture
def salary_inp():
    """Default salaried employee input for quick tests."""
    from services.calculator import PayCalculationInput
    return PayCalculationInput(
        pay_type="salary",
        pay_rate=75000,
        filing_status="single",
        state_code="NY",
        pay_frequency="biweekly",
    )


@pytest.fixture
def hourly_inp():
    """Default hourly employee input."""
    from services.calculator import PayCalculationInput
    return PayCalculationInput(
        pay_type="hourly",
        pay_rate=25.0,
        filing_status="single",
        state_code="TX",
        pay_frequency="biweekly",
        regular_hours=80,
        overtime_hours=0,
    )


# ── Helpers available in all tests ──────────────────────────
def make_inp(**kwargs):
    from services.calculator import PayCalculationInput
    defaults = dict(
        pay_type="salary",
        pay_rate=60000,
        filing_status="single",
        state_code="NY",
        pay_frequency="biweekly",
    )
    defaults.update(kwargs)
    return PayCalculationInput(**defaults)


# Export make_inp so test files can import it
pytest.make_inp = make_inp
