"""
User management — company admins can invite, manage, and deactivate users.
GET    /users           list users in company
POST   /users/invite    send invite (creates inactive user)
PUT    /users/{id}      update role or name
DELETE /users/{id}      deactivate user
GET    /users/me        current user profile
PUT    /users/me        update own profile / change password
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from database import get_db
from models import User, Company
from utils.auth import get_current_user, hash_password, verify_password, create_token

router = APIRouter(prefix="/users", tags=["users"])


class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class InviteRequest(BaseModel):
    email: str
    first_name: str
    last_name: str
    role: str = "viewer"
    temp_password: str = "ChangeMe123!"


class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


@router.get("/me")
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == current_user["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    return _serialize(user)


@router.put("/me")
async def update_me(
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(User).where(User.id == current_user["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    if body.first_name:
        user.first_name = body.first_name
    if body.last_name:
        user.last_name = body.last_name

    if body.new_password:
        if not body.current_password:
            raise HTTPException(400, "current_password required to set new password")
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(400, "Current password is incorrect")
        if len(body.new_password) < 8:
            raise HTTPException(400, "New password must be at least 8 characters")
        user.password_hash = hash_password(body.new_password)

    await db.commit()
    await db.refresh(user)
    return _serialize(user)


@router.get("")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    result = await db.execute(
        select(User)
        .where(User.company_id == current_user["company_id"])
        .order_by(User.created_at)
    )
    users = result.scalars().all()
    return [_serialize(u) for u in users]


@router.post("/invite", status_code=201)
async def invite_user(
    body: InviteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email already registered")

    if body.role not in ("admin", "manager", "viewer"):
        raise HTTPException(400, "role must be admin, manager, or viewer")

    user = User(
        company_id=current_user["company_id"],
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        password_hash=hash_password(body.temp_password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # In production: send invite email with temp password
    return {
        **_serialize(user),
        "temp_password": body.temp_password,
        "note": "Share the temp_password with the user — they should change it on first login.",
    }


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)

    result = await db.execute(
        select(User).where(User.id == user_id, User.company_id == current_user["company_id"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # Prevent last admin from being demoted
    if body.role and body.role != "admin" and user.role == "admin":
        admin_count_result = await db.execute(
            select(User).where(
                User.company_id == current_user["company_id"],
                User.role == "admin",
                User.is_active == True,
            )
        )
        if len(admin_count_result.scalars().all()) <= 1:
            raise HTTPException(400, "Cannot remove the last admin")

    for k, v in body.model_dump(exclude_none=True).items():
        setattr(user, k, v)

    await db.commit()
    await db.refresh(user)
    return _serialize(user)


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _require_admin(current_user)
    if user_id == current_user["sub"]:
        raise HTTPException(400, "Cannot deactivate your own account")

    result = await db.execute(
        select(User).where(User.id == user_id, User.company_id == current_user["company_id"])
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    user.is_active = False
    await db.commit()


def _require_admin(current_user: dict):
    if current_user.get("role") not in ("admin", "manager"):
        raise HTTPException(403, "Admin or manager role required")


def _serialize(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "role": u.role,
        "is_active": u.is_active,
        "last_login": str(u.last_login) if u.last_login else None,
        "created_at": str(u.created_at),
    }
