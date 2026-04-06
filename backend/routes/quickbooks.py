"""
QuickBooks Online integration routes.

OAuth flow:
  1. GET  /quickbooks/connect      → redirect to Intuit OAuth page
  2. GET  /quickbooks/callback     → Intuit redirects here; exchange code → tokens; close popup
  3. GET  /quickbooks/status       → check connection (authenticated)
  4. DELETE /quickbooks/disconnect → revoke & remove connection

Data sync endpoints (all require auth):
  5. GET  /quickbooks/fetch/employees   → pull employees from QB
  6. GET  /quickbooks/fetch/accounts    → pull chart of accounts from QB
  7. POST /quickbooks/sync/employees    → push our employees into QB
  8. POST /quickbooks/sync/payroll/{id} → push a pay run as a QB journal entry
  9. POST /quickbooks/import/employees  → import QB employees into PayrollOS
"""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from utils.auth import get_current_user
from models import QuickBooksConnection, Employee, PayRun, PayRunItem
import services.quickbooks as qb_svc
from config import settings

import asyncio
logger = logging.getLogger("payrollos.routes.quickbooks")
router = APIRouter(prefix="/quickbooks", tags=["QuickBooks"])


# ── Concurrency Control ──────────────────────────────────────────
# Dictionary of locks per company_id to prevent redundant/failing simultaneous refreshes
_refresh_locks: dict[str, asyncio.Lock] = {}

def _get_refresh_lock(company_id: str) -> asyncio.Lock:
    if company_id not in _refresh_locks:
        _refresh_locks[company_id] = asyncio.Lock()
    return _refresh_locks[company_id]


# ── Helpers ──────────────────────────────────────────────────────

async def _get_connection(company_id: str) -> QuickBooksConnection:
    conn = await QuickBooksConnection.find_one(
        QuickBooksConnection.company_id == uuid.UUID(company_id)
    )
    if not conn:
        raise HTTPException(status_code=404, detail="QuickBooks not connected")
    return conn


async def _ensure_fresh_token(conn: QuickBooksConnection) -> str:
    """Return a valid access token, refreshing if needed. Uses a lock to prevent race conditions."""
    if qb_svc.is_token_expired(conn.token_expires_at):
        company_id = str(conn.company_id)
        async with _get_refresh_lock(company_id):
            # Re-check expiration inside the lock (it might have been refreshed by another request)
            # Re-fetch from DB inside lock to get the most recent tokens
            conn = await QuickBooksConnection.find_one({"company_id": conn.company_id})
            if not conn:
                raise HTTPException(404, "Connection lost during refresh")

            if not qb_svc.is_token_expired(conn.token_expires_at):
                return conn.access_token

            logger.info(f"QB access token expired for company {company_id} — refreshing...")
            try:
                token_data = await qb_svc.refresh_access_token(conn.refresh_token)
                parsed = qb_svc.parse_token_response(token_data)
                
                conn.access_token = parsed["access_token"]
                conn.refresh_token = parsed["refresh_token"]
                conn.token_expires_at = parsed["token_expires_at"]
                conn.refresh_expires_at = parsed["refresh_expires_at"]
                await conn.save()
                logger.info(f"Successfully refreshed QB token for company {company_id}")
            except Exception as e:
                logger.error(f"Failed to refresh QB token for company {company_id}: {e}")
                # We don't raise here, but return the old token; calls will fail with 401 anyway
                # unless we want to catch 401 later. For now, we return whatever we have.
    
    return conn.access_token


# ── OAuth: initiate ──────────────────────────────────────────────

@router.get("/auth-url")
async def get_auth_url(current_user: dict = Depends(get_current_user)):
    """Return the Intuit OAuth URL as JSON (frontend opens it in a popup)."""
    company_id = str(current_user["company_id"])
    state = json.dumps({"company_id": company_id, "nonce": str(uuid.uuid4())[:8]})
    import base64 as _b64
    state_b64 = _b64.urlsafe_b64encode(state.encode()).decode()
    return {"url": qb_svc.build_auth_url(state_b64)}


@router.get("/connect")
async def connect_quickbooks(
    current_user: dict = Depends(get_current_user),
):
    """Redirect browser to Intuit OAuth consent screen (server-side redirect)."""
    company_id = str(current_user["company_id"])
    state = json.dumps({"company_id": company_id, "nonce": str(uuid.uuid4())[:8]})
    import base64
    state_b64 = base64.urlsafe_b64encode(state.encode()).decode()
    auth_url = qb_svc.build_auth_url(state_b64)
    return RedirectResponse(url=auth_url)


# ── OAuth: callback (public — called by Intuit redirect) ────────

@router.get("/callback", response_class=HTMLResponse)
async def quickbooks_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    realmId: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Intuit redirects here after user authorises (or denies) access.
    Exchanges auth code for tokens and closes the popup.
    """
    def _close_popup(success: bool, message: str) -> str:
        status = "connected" if success else "error"
        msg = message.replace('"', '\\"')
        return f"""<!DOCTYPE html>
<html>
<head><title>QuickBooks — PayrollOS</title></head>
<body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0f1117;color:#fff">
  <div style="text-align:center">
    <div style="font-size:48px;margin-bottom:16px">{"✓" if success else "✗"}</div>
    <h2 style="margin:0 0 8px">{message}</h2>
    <p style="color:rgba(255,255,255,0.5);font-size:14px">This window will close automatically.</p>
  </div>
  <script>
    window.opener && window.opener.postMessage({{type:"qb_oauth",status:"{status}",message:"{msg}"}}, "*");
    setTimeout(() => window.close(), 2000);
  </script>
</body>
</html>"""

    if error:
        return HTMLResponse(_close_popup(False, f"QuickBooks access denied: {error}"))

    if not code or not state or not realmId:
        return HTMLResponse(_close_popup(False, "Missing required OAuth parameters"))

    # Decode state
    try:
        import base64
        state_data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        company_id = state_data["company_id"]
    except Exception:
        return HTMLResponse(_close_popup(False, "Invalid OAuth state parameter"))

    # Exchange code for tokens
    try:
        token_data = await qb_svc.exchange_code_for_tokens(code)
    except Exception as e:
        logger.error(f"QB token exchange failed: {e}")
        return HTMLResponse(_close_popup(False, "Failed to exchange authorization code"))

    parsed = qb_svc.parse_token_response(token_data)

    # Fetch company name from QB
    qb_company_name = None
    try:
        client = qb_svc.QBClient(
            parsed["access_token"], 
            parsed["refresh_token"],
            realmId
        )
        info = await client.get_company_info()
        qb_company_name = info.get("CompanyName")
    except Exception as e:
        logger.warning(f"Could not fetch QB company name: {e}")

    # Upsert connection record
    try:
        conn = await QuickBooksConnection.find_one(
            QuickBooksConnection.company_id == uuid.UUID(company_id)
        )
        if conn:
            conn.realm_id = realmId
            conn.access_token = parsed["access_token"]
            conn.refresh_token = parsed["refresh_token"]
            conn.token_expires_at = parsed["token_expires_at"]
            conn.refresh_expires_at = parsed["refresh_expires_at"]
            conn.qb_company_name = qb_company_name
            conn.connected_at = datetime.utcnow()
            await conn.save()
        else:
            conn = QuickBooksConnection(
                company_id=uuid.UUID(company_id),
                realm_id=realmId,
                access_token=parsed["access_token"],
                refresh_token=parsed["refresh_token"],
                token_expires_at=parsed["token_expires_at"],
                refresh_expires_at=parsed["refresh_expires_at"],
                qb_company_name=qb_company_name,
                is_sandbox=settings.QB_SANDBOX,
            )
            await conn.insert()
    except Exception as e:
        logger.error(f"Failed to store QB connection: {e}")
        return HTMLResponse(_close_popup(False, "Failed to save QuickBooks connection"))

    company_label = qb_company_name or "your company"
    return HTMLResponse(_close_popup(True, f"Connected to {company_label}!"))


# ── Status ───────────────────────────────────────────────────────

@router.get("/status")
async def get_status(current_user: dict = Depends(get_current_user)):
    """Return QuickBooks connection status for this company."""
    company_id = str(current_user["company_id"])
    conn = await QuickBooksConnection.find_one(
        QuickBooksConnection.company_id == uuid.UUID(company_id)
    )
    if not conn:
        return {"connected": False}

    # Proactively attempt to refresh if expired
    try:
        await _ensure_fresh_token(conn)
        # Re-fetch to get updated stamps
        conn = await QuickBooksConnection.find_one(QuickBooksConnection.company_id == conn.company_id)
    except Exception as e:
        logger.warning(f"Proactive QB refresh failed in status check: {e}")

    token_valid = not qb_svc.is_token_expired(conn.token_expires_at)
    refresh_valid = not qb_svc.is_token_expired(conn.refresh_expires_at, buffer_seconds=0)

    return {
        "connected": True,
        "realm_id": conn.realm_id,
        "qb_company_name": conn.qb_company_name,
        "is_sandbox": conn.is_sandbox,
        "connected_at": conn.connected_at.isoformat(),
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "token_valid": token_valid,
        "refresh_valid": refresh_valid,
        "token_expires_at": conn.token_expires_at.isoformat(),
    }


@router.post("/refresh")
async def force_refresh_token(current_user: dict = Depends(get_current_user)):
    """Force a token refresh for the current company integration."""
    conn = await _get_connection(str(current_user["company_id"]))
    try:
        await _ensure_fresh_token(conn)
        return {"message": "Token refreshed successfully"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {e}")


# ── Disconnect ───────────────────────────────────────────────────

@router.delete("/disconnect")
async def disconnect(current_user: dict = Depends(get_current_user)):
    """Revoke QB tokens and remove connection record."""
    conn = await _get_connection(str(current_user["company_id"]))
    try:
        await qb_svc.revoke_token(conn.refresh_token)
    except Exception as e:
        logger.warning(f"QB token revoke failed (proceeding with disconnect): {e}")
    await conn.delete()
    return {"message": "QuickBooks disconnected"}


# ── Fetch from QB ────────────────────────────────────────────────

@router.get("/fetch/employees")
async def fetch_qb_employees(current_user: dict = Depends(get_current_user)):
    """Pull all employees from QuickBooks."""
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)
    token = await _ensure_fresh_token(conn)
    client = qb_svc.QBClient(token, conn.refresh_token, conn.realm_id)
    employees = await client.get_employees()
    
    # Check which employees are already imported
    existing = await Employee.find(
        Employee.company_id == uuid.UUID(company_id),
        Employee.qb_employee_id != None  # noqa: E711
    ).to_list()
    existing_qb_ids = {e.qb_employee_id for e in existing}

    for emp in employees:
        emp["is_imported"] = emp.get("Id") in existing_qb_ids

    return {"total": len(employees), "employees": employees}


@router.get("/fetch/accounts")
async def fetch_qb_accounts(current_user: dict = Depends(get_current_user)):
    """Pull chart of accounts from QuickBooks."""
    conn = await _get_connection(str(current_user["company_id"]))
    token = await _ensure_fresh_token(conn)
    client = qb_svc.QBClient(token, conn.refresh_token, conn.realm_id)
    accounts = await client.get_accounts()
    return {"total": len(accounts), "accounts": accounts}


@router.get("/fetch/vendors")
async def fetch_qb_vendors(current_user: dict = Depends(get_current_user)):
    """Pull vendors from QuickBooks."""
    conn = await _get_connection(str(current_user["company_id"]))
    token = await _ensure_fresh_token(conn)
    client = qb_svc.QBClient(token, conn.refresh_token, conn.realm_id)
    vendors = await client.get_vendors()
    return {"total": len(vendors), "vendors": vendors}


# ── Sync to QB ───────────────────────────────────────────────────

@router.post("/sync/employees")
async def sync_employees_to_qb(current_user: dict = Depends(get_current_user)):
    """
    Push all active PayrollOS employees into QuickBooks.
    Creates new QB Employee records; skips employees already linked (by qb_employee_id).
    """
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)
    token = await _ensure_fresh_token(conn)
    client = qb_svc.QBClient(token, conn.refresh_token, conn.realm_id)

    employees = await Employee.find(
        Employee.company_id == uuid.UUID(company_id),
        Employee.status == "active",
    ).to_list()

    created = []
    skipped = []
    errors = []

    for emp in employees:
        emp_dict = {
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "email": emp.email,
            "phone": emp.phone,
            "hire_date": str(emp.hire_date) if emp.hire_date else None,
            "job_title": emp.job_title,
            "address_line1": emp.address_line1,
            "city": emp.city,
            "state": emp.state,
            "zip": emp.zip,
            "status": emp.status,
        }
        # Skip if already synced
        if emp.qb_employee_id:
            skipped.append({"id": str(emp.id), "name": emp.full_name, "qb_id": emp.qb_employee_id})
            continue
        try:
            payload = qb_svc.build_employee_payload(emp_dict)
            qb_emp = await client.create_employee(payload)
            qb_id = qb_emp.get("Id")
            # Store QB ID on our employee
            emp.qb_employee_id = qb_id
            await emp.save()
            created.append({"id": str(emp.id), "name": emp.full_name, "qb_id": qb_id})
        except Exception as e:
            logger.error(f"Failed to sync employee {emp.id} to QB: {e}")
            errors.append({"id": str(emp.id), "name": emp.full_name, "error": str(e)})

    conn.last_synced_at = datetime.utcnow()
    await conn.save()

    return {
        "message": f"Sync complete: {len(created)} created, {len(skipped)} skipped, {len(errors)} errors",
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }


class SyncPayrollRequest(BaseModel):
    account_mapping: dict = {}  # optional: {"payroll_expense": "qb_account_id", ...}


@router.post("/sync/payroll/{pay_run_id}")
async def sync_payroll_to_qb(
    pay_run_id: str,
    body: SyncPayrollRequest = SyncPayrollRequest(),
    current_user: dict = Depends(get_current_user),
):
    """
    Push a completed pay run as a Journal Entry in QuickBooks.
    Creates a double-entry: Payroll Expense (debit) / Payroll Liabilities + Clearing (credit).
    """
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)

    # Load pay run
    run = await PayRun.find_one(
        PayRun.id == uuid.UUID(pay_run_id),
        PayRun.company_id == uuid.UUID(company_id),
    )
    if not run:
        raise HTTPException(status_code=404, detail="Pay run not found")
    if run.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed pay runs can be synced")

    items = await PayRunItem.find(
        PayRunItem.pay_run_id == uuid.UUID(pay_run_id)
    ).to_list()

    token = await _ensure_fresh_token(conn)
    client = qb_svc.QBClient(token, conn.refresh_token, conn.realm_id)

    # Default account mapping (user can override)
    accounts = {
        "payroll_expense": "1",
        "payroll_tax_expense": "2",
        "payroll_clearing": "3",
        "tax_liability": "4",
        "benefits_payable": "5",
        **body.account_mapping,
    }

    run_dict = {
        "id": str(run.id),
        "total_gross": float(run.total_gross or 0),
        "total_net": float(run.total_net or 0),
    }
    items_list = [
        {
            "gross_pay": float(i.gross_pay or 0),
            "net_pay": float(i.net_pay or 0),
            "total_employee_taxes": float(i.total_employee_taxes or 0),
            "employer_total": float(i.employer_total or 0),
            "pretax_deductions": float(i.pretax_deductions or 0),
        }
        for i in items
    ]

    period_end = run.created_at.strftime("%Y-%m-%d")
    je_payload = qb_svc.build_payroll_journal_entry(run_dict, items_list, accounts, period_end)

    try:
        je = await client.create_journal_entry(je_payload)
    except Exception as e:
        logger.error(f"Failed to create QB journal entry: {e}")
        raise HTTPException(status_code=502, detail=f"QuickBooks API error: {e}")

    conn.last_synced_at = datetime.utcnow()
    await conn.save()

    return {
        "message": "Journal entry created in QuickBooks",
        "journal_entry_id": je.get("Id"),
        "pay_run_id": pay_run_id,
        "period": period_end,
        "lines": len(je_payload.get("Line", [])),
    }


# ── Import from QB ───────────────────────────────────────────────

class ImportEmployeesRequest(BaseModel):
    qb_employee_ids: list = []  # empty = import all


@router.post("/import/employees")
async def import_employees_from_qb(
    body: ImportEmployeesRequest = ImportEmployeesRequest(),
    current_user: dict = Depends(get_current_user),
):
    """
    Import QuickBooks employees into PayrollOS.
    Skips employees already linked (matched by qb_employee_id).
    """
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)
    token = await _ensure_fresh_token(conn)
    client = qb_svc.QBClient(token, conn.refresh_token, conn.realm_id)

    qb_employees = await client.get_employees()
    if body.qb_employee_ids:
        qb_employees = [e for e in qb_employees if e.get("Id") in body.qb_employee_ids]

    # Build a set of already-linked QB IDs for this company
    existing = await Employee.find(
        Employee.company_id == uuid.UUID(company_id),
        Employee.qb_employee_id != None,  # noqa: E711
    ).to_list()
    existing_qb_ids = {e.qb_employee_id for e in existing}

    imported = []
    skipped = []
    errors = []

    for qb_emp in qb_employees:
        qb_id = qb_emp.get("Id")
        if qb_id in existing_qb_ids:
            skipped.append({"qb_id": qb_id, "name": f"{qb_emp.get('GivenName','')} {qb_emp.get('FamilyName','')}".strip()})
            continue
        try:
            # Parse QB employee fields
            primary_addr = qb_emp.get("PrimaryAddr", {})
            phone_obj = qb_emp.get("PrimaryPhone", {})
            email_obj = qb_emp.get("PrimaryEmailAddr", {})
            hire_date_str = qb_emp.get("HiredDate")
            from datetime import date
            hire_date = None
            if hire_date_str:
                try:
                    hire_date = date.fromisoformat(hire_date_str[:10])
                except Exception:
                    pass

            emp = Employee(
                company_id=uuid.UUID(company_id),
                first_name=qb_emp.get("GivenName", "Unknown"),
                last_name=qb_emp.get("FamilyName", ""),
                email=email_obj.get("Address") if email_obj else None,
                phone=phone_obj.get("FreeFormNumber") if phone_obj else None,
                hire_date=hire_date,
                address_line1=primary_addr.get("Line1"),
                city=primary_addr.get("City"),
                state=primary_addr.get("CountrySubDivisionCode"),
                zip=primary_addr.get("PostalCode"),
                status="active" if qb_emp.get("Active", True) else "inactive",
                pay_type="salary",
                pay_rate=0,
                pay_frequency="biweekly",
                qb_employee_id=qb_id,
            )
            await emp.insert()
            imported.append({
                "id": str(emp.id),
                "qb_id": qb_id,
                "name": emp.full_name,
            })
        except Exception as e:
            logger.error(f"Failed to import QB employee {qb_id}: {e}")
            errors.append({"qb_id": qb_id, "error": str(e)})

    conn.last_synced_at = datetime.utcnow()
    await conn.save()

    return {
        "message": f"Import complete: {len(imported)} imported, {len(skipped)} already linked, {len(errors)} errors",
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }
