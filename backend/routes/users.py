"""
User management — settings, roles, and profile.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from models import User
from utils.auth import get_current_user, hash_password

router = APIRouter(prefix="/users", tags=["users"])


class UserProfileUpdate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr


class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    role: str = "viewer"
    password: str


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    user = await User.get(current_user["sub"])
    if not user:
        raise HTTPException(404, "User not found")
    return _ser(user)


@router.put("/me")
async def update_me(
    body: UserProfileUpdate,
    current_user: dict = Depends(get_current_user)
):
    user = await User.get(current_user["sub"])
    if not user:
        raise HTTPException(404, "User not found")
    
    user.first_name = body.first_name
    user.last_name = body.last_name
    user.email = body.email
    await user.save()
    return _ser(user)


@router.get("")
async def list_users(current_user: dict = Depends(get_current_user)):
    users = await User.find(User.company_id == current_user["company_id"]).to_list()
    return [_ser(u) for u in users]


@router.post("", status_code=201)
async def create_user(
    body: UserCreate,
    current_user: dict = Depends(get_current_user)
):
    # Check if exists
    existing = await User.find_one(User.email == body.email)
    if existing:
        raise HTTPException(400, "User with this email already exists")
    
    user = User(
        company_id=current_user["company_id"],
        email=body.email,
        password_hash=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        role=body.role
    )
    await user.insert()
    return _ser(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    current_user: dict = Depends(get_current_user)
):
    if user_id == current_user["sub"]:
        raise HTTPException(400, "Cannot delete yourself")
    
    user = await User.find_one(
        User.id == user_id, 
        User.company_id == current_user["company_id"]
    )
    if user:
        await user.delete()


def _ser(u: User) -> dict:
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
