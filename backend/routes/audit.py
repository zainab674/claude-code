"""
Audit logging for compliance and security.
Migrated to Beanie (MongoDB).
"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Request
from datetime import datetime
from models import AuditLog
from utils.auth import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def get_audit_logs(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if resource_type:
        query["resource_type"] = resource_type
    if resource_id:
        query["resource_id"] = resource_id
    if user_id:
        query["user_id"] = uuid.UUID(user_id)
        
    logs = await AuditLog.find(query).sort("-created_at").skip(offset).limit(limit).to_list()
    total = await AuditLog.find(query).count()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [_ser(l) for l in logs]
    }


async def log_action(
    request: Request,
    company_id: str,
    user_id: str,
    user_email: str,
    action: str,
    resource_type: str = None,
    resource_id: str = None,
    details: dict = None,
):
    """Internal helper to record an audit log."""
    log = AuditLog(
        company_id=company_id if isinstance(company_id, uuid.UUID) else uuid.UUID(company_id),
        user_id=user_id if not user_id or isinstance(user_id, uuid.UUID) else uuid.UUID(user_id),
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id if not resource_id or isinstance(resource_id, uuid.UUID) else uuid.UUID(resource_id),
        details=details or {},
        ip_address=request.client.host if request else None
    )
    await log.insert()


def _ser(l: AuditLog) -> dict:
    return {
        "id": str(l.id),
        "user_id": str(l.user_id) if l.user_id else None,
        "user_email": l.user_email,
        "action": l.action,
        "resource_type": l.resource_type,
        "resource_id": l.resource_id,
        "details": l.details,
        "ip_address": l.ip_address,
        "created_at": str(l.created_at),
    }
