"""
QBXpress integration routes for PayrollOS.

Connection flow:
  1. GET  /qbxpress/connect          → redirect popup to QBXpress auth page
  2. GET  /qbxpress/callback         → QBXpress posts token here; store it; close popup
  3. GET  /qbxpress/status           → check connection
  4. DELETE /qbxpress/disconnect     → remove connection

Data:
  5. GET  /qbxpress/fetch/company    → pull company info from QBXpress
  6. GET  /qbxpress/fetch/accounts   → pull QB accounts from QBXpress
  7. GET  /qbxpress/fetch/overview   → pull financial overview from QBXpress
  8. POST /qbxpress/sync/payroll/{id} → push pay run to QBXpress
"""
import base64
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from utils.auth import get_current_user
from models import QBXpressConnection, PayRun, PayRunItem, Employee
import services.qbxpress as qbx_svc
from config import settings

logger = logging.getLogger("payrollos.routes.qbxpress")
router = APIRouter(prefix="/qbxpress", tags=["QBXpress"])


# ── Helpers ──────────────────────────────────────────────────────

async def _get_connection(company_id: str) -> QBXpressConnection:
    conn = await QBXpressConnection.find_one(
        QBXpressConnection.company_id == uuid.UUID(company_id)
    )
    if not conn:
        raise HTTPException(status_code=404, detail="QBXpress not connected")
    return conn


# ── OAuth-like Initiation ────────────────────────────────────────

@router.get("/auth-url")
async def get_auth_url(current_user: dict = Depends(get_current_user)):
    """Return the QBXpress authorization URL as JSON (frontend opens it in a popup)."""
    company_id = str(current_user["company_id"])
    state_data = {"company_id": company_id, "nonce": str(uuid.uuid4())[:8]}
    state_b64 = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
    callback_url = f"{settings.PAYROLLOS_BACKEND_URL}/qbxpress/callback"
    connect_url = qbx_svc.build_connect_url(callback_url, state_b64)
    return {"url": connect_url}


@router.get("/connect")
async def connect_qbxpress(current_user: dict = Depends(get_current_user)):
    """Redirect directly to QBXpress authorization page (used for server-side redirects)."""
    company_id = str(current_user["company_id"])
    state_data = {"company_id": company_id, "nonce": str(uuid.uuid4())[:8]}
    state_b64 = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()
    callback_url = f"{settings.PAYROLLOS_BACKEND_URL}/qbxpress/callback"
    connect_url = qbx_svc.build_connect_url(callback_url, state_b64)
    return RedirectResponse(url=connect_url)


# ── Callback (public — called by QBXpress redirect) ─────────────

@router.get("/callback", response_class=HTMLResponse)
async def qbxpress_callback(
    token: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    company_name: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    QBXpress redirects here after user authorizes (or denies).
    Stores the token and sends a postMessage to close the popup.
    """
    def _close_popup(success: bool, message: str) -> str:
        status = "connected" if success else "error"
        msg = message.replace('"', '\\"')
        return f"""<!DOCTYPE html>
<html>
<head><title>QBXpress — PayrollOS</title></head>
<body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0f1117;color:#fff">
  <div style="text-align:center;max-width:340px">
    <div style="font-size:52px;margin-bottom:16px">{"✓" if success else "✗"}</div>
    <h2 style="margin:0 0 8px;font-size:20px">{message}</h2>
    <p style="color:rgba(255,255,255,0.4);font-size:13px">This window will close automatically.</p>
  </div>
  <script>
    window.opener && window.opener.postMessage({{type:"qbx_oauth",status:"{status}",message:"{msg}"}}, "*");
    setTimeout(() => window.close(), 1800);
  </script>
</body>
</html>"""

    if error:
        return HTMLResponse(_close_popup(False, f"QBXpress access denied: {error}"))

    if not token or not state:
        return HTMLResponse(_close_popup(False, "Missing token or state parameter"))

    # Decode state
    try:
        state_data = json.loads(base64.urlsafe_b64decode(state.encode()).decode())
        company_id_local = state_data["company_id"]
    except Exception:
        return HTMLResponse(_close_popup(False, "Invalid state parameter"))

    # Verify token is valid with QBXpress
    try:
        conn_info = await qbx_svc.verify_token(token, qbx_company_id=company_id)
        if not conn_info:
            return HTMLResponse(_close_popup(False, "Token verification failed"))
    except Exception as e:
        logger.error(f"QBXpress token verification error: {e}")
        return HTMLResponse(_close_popup(False, "Could not verify token with QBXpress"))

    # Upsert connection record
    try:
        existing = await QBXpressConnection.find_one(
            QBXpressConnection.company_id == uuid.UUID(company_id_local)
        )
        if existing:
            existing.token = token
            existing.qbx_user_id = user_id or conn_info.get("userId")
            existing.qbx_company_id = company_id or conn_info.get("companyId")
            existing.qbx_company_name = company_name or conn_info.get("companyName")
            existing.connected_at = datetime.utcnow()
            await existing.save()
        else:
            conn = QBXpressConnection(
                company_id=uuid.UUID(company_id_local),
                token=token,
                qbx_user_id=user_id or conn_info.get("userId"),
                qbx_company_id=company_id or conn_info.get("companyId"),
                qbx_company_name=company_name or conn_info.get("companyName"),
            )
            await conn.insert()
    except Exception as e:
        logger.error(f"Failed to store QBXpress connection: {e}")
        return HTMLResponse(_close_popup(False, "Failed to save connection"))

    label = company_name or conn_info.get("companyName") or "your QBXpress account"
    return HTMLResponse(_close_popup(True, f"Connected to {label}!"))


# ── Status ───────────────────────────────────────────────────────

@router.get("/status")
async def get_status(current_user: dict = Depends(get_current_user)):
    company_id = str(current_user["company_id"])
    conn = await QBXpressConnection.find_one(
        QBXpressConnection.company_id == uuid.UUID(company_id)
    )
    if not conn:
        return {"connected": False}
    return {
        "connected": True,
        "qbx_company_name": conn.qbx_company_name,
        "connected_at": conn.connected_at.isoformat(),
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
    }


# ── Disconnect ───────────────────────────────────────────────────

@router.delete("/disconnect")
async def disconnect(current_user: dict = Depends(get_current_user)):
    conn = await _get_connection(str(current_user["company_id"]))
    await conn.delete()
    return {"message": "QBXpress disconnected"}


# ── Fetch from QBXpress ──────────────────────────────────────────

@router.get("/fetch/company")
async def fetch_company(current_user: dict = Depends(get_current_user)):
    conn = await _get_connection(str(current_user["company_id"]))
    data = await qbx_svc.get_company_info(conn.token, qbx_company_id=conn.qbx_company_id)
    return data


@router.get("/fetch/accounts")
async def fetch_accounts(current_user: dict = Depends(get_current_user)):
    conn = await _get_connection(str(current_user["company_id"]))
    accounts = await qbx_svc.get_accounts(conn.token, qbx_company_id=conn.qbx_company_id)
    return {"total": len(accounts), "accounts": accounts}


@router.get("/fetch/overview")
async def fetch_overview(current_user: dict = Depends(get_current_user)):
    conn = await _get_connection(str(current_user["company_id"]))
    data = await qbx_svc.get_financial_overview(conn.token, qbx_company_id=conn.qbx_company_id)
    return data


# ── Push Payroll to QBXpress ─────────────────────────────────────

@router.post("/sync/payroll/{pay_run_id}")
async def sync_payroll(
    pay_run_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Push a completed PayrollOS pay run to QBXpress.
    QBXpress stores it as a payroll sync record visible in its Integrations dashboard.
    """
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)

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

    total_gross = sum(float(i.gross_pay or 0) for i in items)
    total_net = sum(float(i.net_pay or 0) for i in items)
    total_tax = sum(float(i.total_employee_taxes or 0) + float(i.total_employer_taxes or 0) for i in items)

    journal_lines = [
        {"description": "Gross wages expense", "amount": round(total_gross, 2), "type": "debit"},
        {"description": "Net payroll clearing", "amount": round(total_net, 2), "type": "credit"},
        {"description": "Payroll tax liabilities", "amount": round(total_tax, 2), "type": "credit"},
    ]

    period = run.created_at.strftime("%Y-%m-%d")

    try:
        result = await qbx_svc.push_payroll_sync(
            token=conn.token,
            qbx_company_id=conn.qbx_company_id,
            pay_run_id=str(run.id),
            period=period,
            total_gross=round(total_gross, 2),
            total_net=round(total_net, 2),
            total_tax=round(total_tax, 2),
            employee_count=len(items),
            journal_lines=journal_lines,
        )
    except Exception as e:
        logger.error(f"Failed to push payroll to QBXpress: {e}")
        raise HTTPException(status_code=502, detail=f"QBXpress API error: {e}")

    conn.last_synced_at = datetime.utcnow()
    await conn.save()

    return {
        "message": "Payroll synced to QBXpress",
        "period": period,
        "total_gross": total_gross,
        "total_net": total_net,
        "employee_count": len(items),
        "qbxpress_response": result,
    }


@router.post("/sync/employees")
async def sync_employees(current_user: dict = Depends(get_current_user)):
    """
    Pull employees from qbXpress and upsert them into PayrollOS.
    """
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)

    try:
        qbx_employees = await qbx_svc.get_employees(conn.token, qbx_company_id=conn.qbx_company_id)
    except Exception as e:
        logger.error(f"Failed to fetch employees from qbXpress: {e}")
        raise HTTPException(status_code=502, detail=f"QBXpress API error: {e}")

    synced_count = 0
    for qe in qbx_employees:
        # Try to find existing by qb_employee_id or email
        existing = await Employee.find_one(
            Employee.company_id == uuid.UUID(company_id),
            {"$or": [{"qb_employee_id": str(qe["id"])}, {"email": qe.get("email")}]}
        )

        if existing:
            # Update
            existing.first_name = qe.get("firstName") or existing.first_name
            existing.last_name = qe.get("lastName") or existing.last_name
            existing.email = qe.get("email") or existing.email
            existing.phone = qe.get("phone") or existing.phone
            existing.address_line1 = qe.get("address") or existing.address_line1
            existing.qb_employee_id = str(qe["id"])
            existing.updated_at = datetime.utcnow()
            await existing.save()
        else:
            # Create
            new_emp = Employee(
                company_id=uuid.UUID(company_id),
                first_name=qe.get("firstName") or qe.get("name") or "Unknown",
                last_name=qe.get("lastName") or "",
                email=qe.get("email"),
                phone=qe.get("phone"),
                address_line1=qe.get("address"),
                pay_rate=Decimal(str(qe.get("hourlyRate", 0))),
                pay_type="hourly" if qe.get("hourlyRate") else "salary",
                qb_employee_id=str(qe["id"]),
            )
            await new_emp.insert()
        synced_count += 1

    conn.last_synced_at = datetime.utcnow()
    await conn.save()

    return {
        "message": f"Successfully synced {synced_count} employees from qbXpress",
        "count": synced_count
    }


@router.post("/sync/employees/push")
async def push_employees_to_qbx(current_user: dict = Depends(get_current_user)):
    """
    Push active PayrollOS employees to qbXpress.
    """
    company_id = str(current_user["company_id"])
    conn = await _get_connection(company_id)

    employees = await Employee.find(
        Employee.company_id == uuid.UUID(company_id),
        Employee.status == "active"
    ).to_list()

    if not employees:
        return {"message": "No active employees to sync", "count": 0}

    # Map to qbXpress format
    push_data = []
    for emp in employees:
        push_data.append({
            "id": str(emp.id),
            "firstName": emp.first_name,
            "lastName": emp.last_name,
            "name": emp.full_name,
            "email": emp.email,
            "phone": emp.phone,
            "address": emp.address_line1,
            "hiredDate": emp.hire_date.isoformat() if emp.hire_date else None,
            "hourlyRate": float(emp.pay_rate) if emp.pay_rate else 0,
            "isActive": True
        })

    try:
        result = await qbx_svc.push_employees(conn.token, qbx_company_id=conn.qbx_company_id, employees=push_data)
    except Exception as e:
        logger.error(f"Failed to push employees to qbXpress: {e}")
        raise HTTPException(status_code=502, detail=f"QBXpress API error: {e}")

    conn.last_synced_at = datetime.utcnow()
    await conn.save()

    return {
        "message": result.get("message", f"Successfully synced {len(employees)} employees to qbXpress"),
        "count": len(employees),
        "results": result.get("results")
    }
