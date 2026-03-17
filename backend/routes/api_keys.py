import uuid
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from models import ApiKey
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

# Header name for API key auth
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


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
) -> Optional[dict]:
    """
    Dependency: authenticate via X-API-Key header.
    Returns a user-like dict so routes work with both JWT and API key.
    """
    if not api_key:
        return None
    key_hash = _hash_key(api_key)
    key_obj = await ApiKey.find_one(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    
    if not key_obj:
        return None
    if key_obj.expires_at and datetime.utcnow() > key_obj.expires_at:
        return None
        
    # Update last_used (fire-and-forget style)
    key_obj.last_used = datetime.utcnow()
    await key_obj.save()
    
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
    current_user: dict = Depends(get_current_user),
):
    keys = await ApiKey.find(ApiKey.company_id == current_user["company_id"]).sort("-created_at").to_list()
    return [_serialize(k) for k in keys]


@router.post("", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Only admins can create API keys")

    raw_key = _generate_key(body.environment)

    expires_at = None
    if body.expires_days:
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
    await key_obj.insert()

    return {
        **_serialize(key_obj),
        "key": raw_key,   # shown ONCE — not stored
        "warning": "Copy this key now — it will not be shown again.",
    }


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Only admins can revoke API keys")
        
    key_obj = await ApiKey.find_one(
        ApiKey.id == UUID(key_id),
        ApiKey.company_id == current_user["company_id"],
    )
    if not key_obj:
        raise HTTPException(404, "API key not found")
        
    key_obj.is_active = False
    await key_obj.save()


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
