"""
Audit log route + helper function used throughout the app.
Usage:
    from routes.audit import log_action
    await log_action(db, current_user, "employee.created", "employee", str(emp.id), {"name": emp.full_name})
"""
from datetime import datetime
from typing import Optional, Any
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from database import get_db
from models_audit import AuditLog
from utils.auth import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


async def log_action(
    db: AsyncSession,
    current_user: dict,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: Optional[dict] = None,
    ip_address: str = "",
):
    """
    Record an audit event. Call this after any significant action.

    Common action strings:
        auth.login              auth.logout         auth.password_reset
        employee.created        employee.updated    employee.terminated
        payroll.preview         payroll.run         payroll.run_failed
        paystub.downloaded      paystub.viewed
        company.updated         user.created
        export.employees        export.payroll
        import.employees
    """
    entry = AuditLog(
        company_id=current_user.get("company_id"),
        user_id=current_user.get("sub"),
        user_email=current_user.get("email", ""),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
    )
    db.add(entry)
    # Don't commit here — caller handles commit


@router.get("")
async def list_audit_logs(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get audit log for the company — most recent first."""
    # Check table exists (graceful if migration not run yet)
    try:
        await db.execute(text("SELECT 1 FROM audit_logs LIMIT 1"))
    except Exception:
        return {"total": 0, "logs": [], "note": "Run: ALTER TABLE — add audit_logs table via migration"}

    q = select(AuditLog).where(AuditLog.company_id == current_user["company_id"])
    if action:
        q = q.where(AuditLog.action.ilike(f"%{action}%"))
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    if resource_id:
        q = q.where(AuditLog.resource_id == resource_id)
    q = q.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "total": len(logs),
        "logs": [
            {
                "id": str(log.id),
                "user_email": log.user_email,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "created_at": str(log.created_at),
            }
            for log in logs
        ],
    }
