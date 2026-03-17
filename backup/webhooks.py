"""
Webhook system — fire HTTP POST to registered URLs when payroll events occur.

Supported events:
  payroll.run.completed     — after every successful pay run
  payroll.run.failed        — on error
  employee.created
  employee.updated
  employee.terminated
  paystub.generated

POST /webhooks          register a webhook endpoint
GET  /webhooks          list webhooks
DELETE /webhooks/{id}   remove webhook

Delivery: async background task, retries up to 3 times with exponential backoff.
Payload signed with HMAC-SHA256 using the webhook's secret.
"""
import uuid
import json
import hmac
import hashlib
import asyncio
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel, HttpUrl
import httpx
from database import Base, get_db
from utils.auth import get_current_user
from config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Model ─────────────────────────────────────────────────────
class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    url = Column(Text, nullable=False)
    secret = Column(String(64), nullable=False)   # HMAC signing secret
    events = Column(Text, default="*")            # comma-separated or "*" for all
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_triggered = Column(DateTime(timezone=True))
    failure_count = Column(String(10), default="0")


class WebhookDeliveryLog(Base):
    __tablename__ = "webhook_deliveries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id", ondelete="CASCADE"))
    event = Column(String(100))
    payload_summary = Column(Text)
    status_code = Column(String(10))
    success = Column(Boolean, default=False)
    attempt = Column(String(5), default="1")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Pydantic schemas ──────────────────────────────────────────
class WebhookCreate(BaseModel):
    url: str
    secret: str
    events: str = "*"   # "*" or "payroll.run.completed,employee.created" etc.


# ── Routes ───────────────────────────────────────────────────
@router.get("")
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Webhook).where(Webhook.company_id == current_user["company_id"])
    )
    hooks = result.scalars().all()
    return [_serialize(h) for h in hooks]


@router.post("", status_code=201)
async def create_webhook(
    body: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not body.url.startswith("https://") and not body.url.startswith("http://localhost"):
        raise HTTPException(400, "Webhook URL must use HTTPS (http://localhost allowed for dev)")

    hook = Webhook(
        company_id=current_user["company_id"],
        url=body.url,
        secret=body.secret,
        events=body.events,
    )
    db.add(hook)
    await db.commit()
    await db.refresh(hook)
    return _serialize(hook)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.company_id == current_user["company_id"],
        )
    )
    hook = result.scalar_one_or_none()
    if not hook:
        raise HTTPException(404, "Webhook not found")
    await db.delete(hook)
    await db.commit()


@router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Send a test ping to the webhook URL."""
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id,
            Webhook.company_id == current_user["company_id"],
        )
    )
    hook = result.scalar_one_or_none()
    if not hook:
        raise HTTPException(404, "Webhook not found")

    payload = {
        "event": "webhook.test",
        "timestamp": datetime.utcnow().isoformat(),
        "company_id": str(hook.company_id),
        "data": {"message": "This is a test ping from PayrollOS"},
    }
    success, status = await _deliver(hook.url, hook.secret, payload)
    return {"success": success, "status_code": status, "url": hook.url}


# ── Delivery logic ────────────────────────────────────────────
def _sign_payload(secret: str, body: bytes) -> str:
    """HMAC-SHA256 signature — verify on your server with the same secret."""
    return "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()


async def _deliver(url: str, secret: str, payload: dict, timeout: int = 10) -> tuple[bool, int]:
    """Attempt a single delivery. Returns (success, status_code)."""
    body = json.dumps(payload).encode()
    sig = _sign_payload(secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-PayrollOS-Signature": sig,
        "X-PayrollOS-Event": payload.get("event", "unknown"),
        "User-Agent": "PayrollOS-Webhook/1.0",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, content=body, headers=headers)
            return resp.status_code < 400, resp.status_code
    except Exception as e:
        return False, 0


async def fire_event(event: str, company_id: str, data: dict):
    """
    Fire a webhook event to all active registered endpoints for a company.
    Call this from routes after significant actions.

    Usage:
        await fire_event("payroll.run.completed", str(company_id), {
            "pay_run_id": str(run.id),
            "total_net": float(run.total_net),
            "employee_count": run.employee_count,
        })
    """
    engine = create_async_engine(
        settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=2,
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(
            select(Webhook).where(
                Webhook.company_id == company_id,
                Webhook.is_active == True,
            )
        )
        hooks = result.scalars().all()

    payload = {
        "event": event,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "company_id": company_id,
        "data": data,
    }

    for hook in hooks:
        # Check if hook subscribes to this event
        if hook.events != "*":
            subscribed = [e.strip() for e in hook.events.split(",")]
            if event not in subscribed:
                continue

        # Retry up to 3 times with backoff: 0s, 2s, 8s
        for attempt in range(1, 4):
            success, status = await _deliver(hook.url, hook.secret, payload)
            if success:
                break
            if attempt < 3:
                await asyncio.sleep(2 ** (attempt - 1) * 2)


def _serialize(h: Webhook) -> dict:
    return {
        "id": str(h.id),
        "url": h.url,
        "events": h.events,
        "is_active": h.is_active,
        "last_triggered": str(h.last_triggered) if h.last_triggered else None,
        "created_at": str(h.created_at),
    }
