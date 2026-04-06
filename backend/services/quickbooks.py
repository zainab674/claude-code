"""
QuickBooks Online integration service.
Handles OAuth 2.0 flow, token management, and all QB API operations.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.base import Ref
from quickbooks.objects.employee import Employee
from quickbooks.objects.account import Account
from quickbooks.objects.vendor import Vendor
from quickbooks.objects.customer import Customer
from quickbooks.objects.journalentry import JournalEntry, JournalEntryLine, JournalEntryLineDetail

from config import settings

logger = logging.getLogger("payrollos.quickbooks")

# QuickBooks Configuration
QB_ENVIRONMENT = "sandbox" if getattr(settings, "QB_SANDBOX", True) else "production"


def get_auth_client() -> AuthClient:
    """Initialize the Intuit OAuth 2.0 AuthClient."""
    return AuthClient(
        client_id=settings.QB_CLIENT_ID,
        client_secret=settings.QB_CLIENT_SECRET,
        redirect_uri=settings.QB_REDIRECT_URI,
        environment=QB_ENVIRONMENT,
    )


# ── OAuth Flow ──────────────────────────────────────────────────

def build_auth_url(state: str) -> str:
    """Construct the Intuit OAuth 2.0 authorization URL."""
    auth_client = get_auth_client()
    return auth_client.get_authorization_url([Scopes.ACCOUNTING, Scopes.OPENID, Scopes.PROFILE, Scopes.EMAIL], state)


async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    auth_client = get_auth_client()
    auth_client.get_bearer_token(code)
    return {
        "access_token": auth_client.access_token,
        "refresh_token": auth_client.refresh_token,
        "expires_in": auth_client.expires_in,
        "x_refresh_token_expires_in": auth_client.x_refresh_token_expires_in,
    }


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """Use refresh token to get a new access token."""
    auth_client = get_auth_client()
    auth_client.refresh(refresh_token=refresh_token)
    return {
        "access_token": auth_client.access_token,
        "refresh_token": auth_client.refresh_token,
        "expires_in": auth_client.expires_in,
        "x_refresh_token_expires_in": auth_client.x_refresh_token_expires_in,
    }


async def revoke_token(token: str) -> None:
    """Revoke an access or refresh token."""
    auth_client = get_auth_client()
    auth_client.revoke(token=token)


# ── Token Helpers ────────────────────────────────────────────────

def parse_token_response(token_data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse QB token response into stored fields."""
    now = datetime.utcnow()
    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "token_expires_at": now + timedelta(seconds=int(token_data.get("expires_in", 3600))),
        "refresh_expires_at": now + timedelta(seconds=int(token_data.get("x_refresh_token_expires_in", 8726400))),
    }


def is_token_expired(expires_at: datetime, buffer_seconds: int = 120) -> bool:
    """Return True if token expires within the buffer window."""
    return datetime.utcnow() >= (expires_at - timedelta(seconds=buffer_seconds))


# ── QB API Client ────────────────────────────────────────────────

class QBClient:
    """Async-friendly wrapper around the python-quickbooks SDK."""

    def __init__(self, access_token: str, refresh_token: str, realm_id: str):
        self.auth_client = get_auth_client()
        self.auth_client.access_token = access_token
        self.auth_client.refresh_token = refresh_token
        self.realm_id = realm_id

        self.client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=refresh_token,
            company_id=realm_id,
            minorversion=75,
        )

        # Force session initialization if library didn't do it
        if not self.client.session:
            self.client._start_session()

    async def get_company_info(self) -> Dict[str, Any]:
        """Fetch company metadata using the SDK."""
        # Using a raw query or direct fetch if available in SDK
        from quickbooks.objects.companyinfo import CompanyInfo
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        loop = asyncio.get_event_loop()
        # The python-quickbooks SDK is blocking, so we run it in a threadpool
        info = await loop.run_in_executor(None, CompanyInfo.get, self.realm_id, self.client)
        return info.to_json() if info else {}

    async def get_employees(self) -> List[Dict[str, Any]]:
        """Fetch all employees."""
        import asyncio
        import json
        from functools import partial
        loop = asyncio.get_event_loop()
        objs = await loop.run_in_executor(None, partial(Employee.all, qb=self.client))
        return [json.loads(o.to_json()) for o in objs]

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Fetch all accounts."""
        import asyncio
        import json
        from functools import partial
        loop = asyncio.get_event_loop()
        objs = await loop.run_in_executor(None, partial(Account.all, qb=self.client))
        return [json.loads(o.to_json()) for o in objs]

    async def get_vendors(self) -> List[Dict[str, Any]]:
        """Fetch all vendors."""
        import asyncio
        import json
        from functools import partial
        loop = asyncio.get_event_loop()
        objs = await loop.run_in_executor(None, partial(Vendor.all, qb=self.client))
        return [json.loads(o.to_json()) for o in objs]

    async def create_employee(self, employee_obj: Employee) -> Dict[str, Any]:
        """Save a new employee to QuickBooks."""
        import asyncio
        import json
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, employee_obj.save, self.client)
        return json.loads(res.to_json()) if res else {}

    async def update_employee(self, employee_obj: Employee) -> Dict[str, Any]:
        """Update an existing employee."""
        import asyncio
        import json
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, employee_obj.save, self.client)
        return json.loads(res.to_json()) if res else {}

    async def create_journal_entry(self, journal_obj: JournalEntry) -> Dict[str, Any]:
        """Post a payroll journal entry."""
        import asyncio
        import json
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, journal_obj.save, self.client)
        return json.loads(res.to_json()) if res else {}


# ── Object Builders ──────────────────────────────────────────────

def build_employee_payload(emp_data: Dict[str, Any]) -> Employee:
    """Convert dict data to a python-quickbooks Employee object."""
    employee = Employee()
    employee.GivenName = emp_data.get("first_name", "")
    employee.FamilyName = emp_data.get("last_name", "")
    employee.Active = emp_data.get("status", "active") == "active"

    if emp_data.get("email"):
        from quickbooks.objects.base import EmailAddress
        employee.PrimaryEmailAddr = EmailAddress()
        employee.PrimaryEmailAddr.Address = emp_data["email"]

    if emp_data.get("phone"):
        from quickbooks.objects.base import PhoneNumber
        employee.PrimaryPhone = PhoneNumber()
        employee.PrimaryPhone.FreeFormNumber = emp_data["phone"]

    if emp_data.get("address_line1"):
        from quickbooks.objects.base import Address
        employee.PrimaryAddr = Address()
        employee.PrimaryAddr.Line1 = emp_data["address_line1"]
        employee.PrimaryAddr.City = emp_data.get("city")
        employee.PrimaryAddr.CountrySubDivisionCode = emp_data.get("state")
        employee.PrimaryAddr.PostalCode = emp_data.get("zip")

    # Important: library defaults this to "", which QB rejects. 
    # Must be None or a valid YYYY-MM-DD string.
    employee.ReleasedDate = None

    return employee


def build_payroll_journal_entry(
    pay_run: Dict[str, Any],
    items: List[Dict[str, Any]],
    accounts: Dict[str, str],
    period_end: str,
) -> JournalEntry:
    """
    Build a python-quickbooks JournalEntry object from a PayRun.
    """
    journal = JournalEntry()
    journal.TxnDate = period_end
    journal.PrivateNote = f"PayrollOS — Pay Run ID: {pay_run.get('id', '')} | {len(items)} employees"

    line_items = []

    total_gross = sum(float(i.get("gross_pay", 0)) for i in items)
    total_employer_taxes = sum(float(i.get("employer_total", 0)) for i in items)
    total_net = sum(float(i.get("net_pay", 0)) for i in items)
    total_employee_taxes = sum(float(i.get("total_employee_taxes", 0)) for i in items)
    total_deductions = sum(float(i.get("pretax_deductions", 0)) for i in items)

    def add_line(amount: float, account_id: str, account_name: str, posting_type: str, description: str):
        line = JournalEntryLine()
        line.Amount = round(amount, 2)
        line.Description = description
        line.DetailType = "JournalEntryLineDetail"

        account_ref = Ref()
        account_ref.value = account_id
        account_ref.name = account_name

        detail = JournalEntryLineDetail()
        detail.PostingType = posting_type
        detail.AccountRef = account_ref

        line.JournalEntryLineDetail = detail
        line_items.append(line)

    # Debit: Payroll Expense (gross wages)
    add_line(total_gross, accounts.get("payroll_expense", "1"), "Payroll Expenses", "Debit",
             f"Gross wages — payroll run {pay_run.get('id', '')}")

    # Debit: Payroll Tax Expense (employer share)
    if total_employer_taxes > 0:
        add_line(total_employer_taxes, accounts.get("payroll_tax_expense", "2"), "Payroll Tax Expense", "Debit",
                 "Employer payroll taxes (FICA, FUTA, SUTA)")

    # Credit: Net Payroll Clearing (amount to be paid out)
    add_line(total_net, accounts.get("payroll_clearing", "3"), "Payroll Clearing", "Credit",
             "Net payroll to be disbursed")

    # Credit: Payroll Tax Liabilities (employee + employer)
    total_tax_liability = total_employee_taxes + total_employer_taxes
    if total_tax_liability > 0:
        add_line(total_tax_liability, accounts.get("tax_liability", "4"), "Payroll Tax Liabilities", "Credit",
                 "Payroll tax liabilities (employee + employer)")

    # Credit: Benefits/Deductions Payable
    if total_deductions > 0:
        add_line(total_deductions, accounts.get("benefits_payable", "5"), "Benefits Payable", "Credit",
                 "Employee pre-tax deductions payable")

    journal.Line = line_items
    return journal
