"""
In-app notification center.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from beanie.operators import In
from models import Notification
from utils.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    comp_id = current_user["company_id"]
    user_id = current_user["sub"]
    
    # query for notifications for this company that are either for this user or broadcast
    query = {
        "company_id": comp_id,
        "$or": [
            {"user_id": user_id},
            {"user_id": None}
        ]
    }
    
    if unread_only:
        query["is_read"] = False
        
    notifications = await Notification.find(query).sort("-created_at").limit(limit).to_list()
    
    unread_count = await Notification.find(
        {
            "company_id": comp_id,
            "is_read": False,
            "$or": [{"user_id": user_id}, {"user_id": None}]
        }
    ).count()

    return {
        "unread_count": unread_count,
        "notifications": [_ser(n) for n in notifications],
    }


@router.post("/{notification_id}/read", status_code=200)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    notif = await Notification.find_one(
        Notification.id == notification_id,
        Notification.company_id == current_user["company_id"]
    )
    if not notif:
        raise HTTPException(404, "Notification not found")
    
    notif.is_read = True
    notif.read_at = datetime.utcnow()
    await notif.save()
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_read(
    current_user: dict = Depends(get_current_user),
):
    comp_id = current_user["company_id"]
    user_id = current_user["sub"]
    
    await Notification.find(
        {
            "company_id": comp_id,
            "is_read": False,
            "$or": [{"user_id": user_id}, {"user_id": None}]
        }
    ).update({"$set": {"is_read": True, "read_at": datetime.utcnow()}})
    
    return {"message": "All notifications marked as read"}


@router.delete("/{notification_id}", status_code=204)
async def dismiss_notification(
    notification_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    notif = await Notification.find_one(
        Notification.id == notification_id,
        Notification.company_id == current_user["company_id"]
    )
    if notif:
        await notif.delete()


# ── Internal helper — called by other services ─────────────────
async def create_notification(
    company_id: str,
    notif_type: str,
    title: str,
    body: str = "",
    action_url: str = "",
    severity: str = "info",
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Create a notification."""
    notif = Notification(
        company_id=company_id if isinstance(company_id, uuid.UUID) else uuid.UUID(company_id),
        user_id=user_id if not user_id or isinstance(user_id, uuid.UUID) else uuid.UUID(user_id),
        type=notif_type,
        title=title,
        body=body,
        action_url=action_url,
        severity=severity,
        metadata=metadata or {},
    )
    await notif.insert()


def _ser(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "action_url": n.action_url,
        "severity": n.severity,
        "is_read": n.is_read,
        "metadata": n.metadata or {},
        "created_at": str(n.created_at),
        "read_at": str(n.read_at) if n.read_at else None,
    }
