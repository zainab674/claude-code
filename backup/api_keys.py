"""
API Key management — machine-to-machine authentication.
Instead of user JWTs, external integrations use long-lived API keys.

POST   /api-keys          create key
GET    /api-keys          list keys (secrets masked)
DELETE /api-keys/{id}     revoke key

Keys are prefixed: pk_live_... or pk_test_...
The raw key is shown ONCE at creation; only the hash is stored.
"""
import uuid
import secrets
import hashlib
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

# Header name for API key auth
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Model ──────────────────────────────────────────────────────
class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)
    key_prefix = Column(String(20), nullable=False)   # first 12 chars for display
    environment = Column(String(10), default="live")  # live | test
    scopes = Column(Text, default="*")                # comma-sep or "*"
    is_active = Column(Boolean, default=True)
    last_used = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)


# ── Schemas ────────────────────────────────────────────────────
class ApiKeyCreate(BaseModel):
    name: str
    environment: str = "live"
    scopes: str = "*"
    expires_days: Optional[int] = None   # None = never expires


# ── Helpers ────────────────────────────────────────────────────
def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_key(env: str) -> str:
    prefix = "pk_live_" if env == "live" else "pk_test_"
    return prefix + secrets.token_urlsafe(32)


# ── Auth dependency ────────────────────────────────────────────
async def get_api_key_user(
    api_key: Optional[str] = Security(API_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> Optional[dict]:
    """
    Dependency: authenticate via X-API-Key header.
    Returns a user-like dict so routes work with both JWT and API key.
    """
    if not api_key:
        return None
    key_hash = _hash_key(api_key)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        return None
    if key_obj.expires_at and datetime.utcnow() > key_obj.expires_at:
        return None
    # Update last_used (fire-and-forget style)
    key_obj.last_used = datetime.utcnow()
    await db.commit()
    return {
        "sub": str(key_obj.id),
        "company_id": str(key_obj.company_id),
        "role": "admin",   # API keys have full access within their scopes
        "email": f"apikey:{key_obj.name}",
        "scopes": key_obj.scopes,
    }


# ── Routes ─────────────────────────────────────────────────────
@router.get("")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiKey).where(ApiKey.company_id == current_user["company_id"])
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [_serialize(k) for k in keys]


@router.post("", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Only admins can create API keys")

    raw_key = _generate_key(body.environment)

    expires_at = None
    if body.expires_days:
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(days=body.expires_days)

    key_obj = ApiKey(
        company_id=current_user["company_id"],
        name=body.name,
        key_hash=_hash_key(raw_key),
        key_prefix=raw_key[:16],
        environment=body.environment,
        scopes=body.scopes,
        expires_at=expires_at,
    )
    db.add(key_obj)
    await db.commit()
    await db.refresh(key_obj)

    return {
        **_serialize(key_obj),
        "key": raw_key,   # shown ONCE — not stored
        "warning": "Copy this key now — it will not be shown again.",
    }


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Only admins can revoke API keys")
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.company_id == current_user["company_id"],
        )
    )
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(404, "API key not found")
    key_obj.is_active = False
    await db.commit()


def _serialize(k: ApiKey) -> dict:
    return {
        "id": str(k.id),
        "name": k.name,
        "key_prefix": k.key_prefix + "...",
        "environment": k.environment,
        "scopes": k.scopes,
        "is_active": k.is_active,
        "last_used": str(k.last_used) if k.last_used else None,
        "expires_at": str(k.expires_at) if k.expires_at else None,
        "created_at": str(k.created_at),
    }
