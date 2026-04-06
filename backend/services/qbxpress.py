"""
QBXpress integration service.
Handles connection to the QBXpress platform using token-based auth.
"""
import logging
import httpx
from typing import Optional, Dict, Any, List
from config import settings

logger = logging.getLogger("payrollos.qbxpress")

QBXPRESS_BASE = getattr(settings, 'QBXPRESS_API_URL', 'http://localhost:5000')


def _auth_headers(token: str, qbx_company_id: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if qbx_company_id:
        headers["X-Company-ID"] = qbx_company_id
    return headers


# ── Connection ───────────────────────────────────────────────────

def build_connect_url(callback_url: str, state: str) -> str:
    """Build the QBXpress authorization page URL (for popup redirect)."""
    qbx_frontend = getattr(settings, 'QBXPRESS_FRONTEND_URL', 'http://localhost:9000')
    return f"{qbx_frontend}/payroll-connect?callback={callback_url}&state={state}"


async def verify_token(token: str, qbx_company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Verify a QBXpress token and return the connection info."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{QBXPRESS_BASE}/api/payroll-connect/verify",
            headers=_auth_headers(token, qbx_company_id),
        )
        if resp.status_code == 200:
            return resp.json()
        return None


# ── Data Fetch ───────────────────────────────────────────────────

async def get_company_info(token: str, qbx_company_id: Optional[str] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{QBXPRESS_BASE}/api/payroll-connect/company",
            headers=_auth_headers(token, qbx_company_id),
        )
        resp.raise_for_status()
        return resp.json()


async def get_accounts(token: str, qbx_company_id: Optional[str] = None) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{QBXPRESS_BASE}/api/payroll-connect/accounts",
            headers=_auth_headers(token, qbx_company_id),
        )
        resp.raise_for_status()
        return resp.json().get("accounts", [])


async def get_financial_overview(token: str, qbx_company_id: Optional[str] = None) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{QBXPRESS_BASE}/api/payroll-connect/overview",
            headers=_auth_headers(token, qbx_company_id),
        )
        resp.raise_for_status()
        return resp.json()


# ── Push Payroll ─────────────────────────────────────────────────

async def push_payroll_sync(
    token: str,
    qbx_company_id: str,
    pay_run_id: str,
    period: str,
    total_gross: float,
    total_net: float,
    total_tax: float,
    employee_count: int,
    journal_lines: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Push a completed payroll run to QBXpress for record-keeping."""
    payload = {
        "payRunId": pay_run_id,
        "period": period,
        "totalGross": total_gross,
        "totalNet": total_net,
        "totalTax": total_tax,
        "employeeCount": employee_count,
        "journalLines": journal_lines,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{QBXPRESS_BASE}/api/payroll-connect/payroll-sync",
            headers=_auth_headers(token, qbx_company_id),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

async def get_employees(token: str, qbx_company_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch employees from qbXpress."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{QBXPRESS_BASE}/api/payroll-connect/employees",
            headers=_auth_headers(token, qbx_company_id),
        )
        resp.raise_for_status()
        return resp.json().get("employees", [])


async def push_employees(token: str, qbx_company_id: str, employees: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Push PayrollOS employees to qbXpress."""
    payload = {"employees": employees}
    async with httpx.AsyncClient(timeout=25) as client:
        resp = await client.post(
            f"{QBXPRESS_BASE}/api/payroll-connect/employees-sync",
            headers=_auth_headers(token, qbx_company_id),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
