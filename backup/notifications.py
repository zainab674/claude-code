"""
In-app notification center.
Notifications are created automatically by the system when:
  - Payroll run completes
  - Paystub is ready
  - PTO request needs review
  - Compliance issue detected
  - Leave request submitted
  - Onboarding task overdue
  - Document uploaded

GET    /notifications          list unread + recent
POST   /notifications/{id}/read  mark as read
POST   /notifications/read-all   mark all as read
DELETE /notifications/{id}       dismiss
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, select, func, update
from sqlalchemy.dialects.postgresql import UUID, JSONB
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    # None user_id = broadcast to all admins
    type = Column(String(50), nullable=False)    # payroll_complete|paystub_ready|pto_request|compliance|etc.
    title = Column(String(255), nullable=False)
    body = Column(Text)
    action_url = Column(String(500))            # frontend route to navigate to
    severity = Column(String(20), default="info")  # info|success|warning|critical
    is_read = Column(Boolean, default=False)
    metadata = Column(JSONB, default=dict)       # extra data (pay_run_id, employee_id, etc.)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    read_at = Column(DateTime(timezone=True))


@router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(Notification).where(
        Notification.company_id == current_user["company_id"],
        (Notification.user_id == current_user["sub"]) | (Notification.user_id == None),
    )
    if unread_only:
        q = q.where(Notification.is_read == False)
    q = q.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(q)
    notifications = result.scalars().all()

    unread_res = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.company_id == current_user["company_id"],
            Notification.is_read == False,
            (Notification.user_id == current_user["sub"]) | (Notification.user_id == None),
        )
    )
    unread_count = unread_res.scalar() or 0

    return {
        "unread_count": unread_count,
        "notifications": [_ser(n) for n in notifications],
    }


@router.post("/{notification_id}/read", status_code=200)
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.company_id == current_user["company_id"],
        )
    )
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.is_read = True
    notif.read_at = datetime.utcnow()
    await db.commit()
    return {"message": "Marked as read"}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(
            Notification.company_id == current_user["company_id"],
            Notification.is_read == False,
            (Notification.user_id == current_user["sub"]) | (Notification.user_id == None),
        )
        .values(is_read=True, read_at=datetime.utcnow())
    )
    await db.commit()
    return {"message": "All notifications marked as read"}


@router.delete("/{notification_id}", status_code=204)
async def dismiss_notification(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.company_id == current_user["company_id"],
        )
    )
    notif = result.scalar_one_or_none()
    if notif:
        await db.delete(notif)
        await db.commit()


# ── Internal helper — called by other services ─────────────────
async def create_notification(
    db: AsyncSession,
    company_id: str,
    notif_type: str,
    title: str,
    body: str = "",
    action_url: str = "",
    severity: str = "info",
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """Create a notification. Call this from other routes after significant events."""
    notif = Notification(
        company_id=company_id,
        user_id=user_id,
        type=notif_type,
        title=title,
        body=body,
        action_url=action_url,
        severity=severity,
        metadata=metadata or {},
    )
    db.add(notif)
    # Don't commit here — caller handles commit


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
