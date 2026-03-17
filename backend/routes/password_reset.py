from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models import User, Company
from utils.auth import hash_password
from services.email import send_password_reset

router = APIRouter(prefix="/auth", tags=["auth"])

# Token storage via in-memory service
from services.token_service import store_reset_token, consume_reset_token


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(req: ForgotRequest):
    user = await User.find_one(User.email == req.email)
    # Always return 200 — don't leak whether email exists
    if not user:
        return {"message": "If that email exists, a reset link has been sent"}

    token = secrets.token_urlsafe(32)
    await store_reset_token(token, str(user.id), ttl_seconds=3600)

    # Load company name for email
    company = await Company.find_one(Company.id == user.company_id)
    company_name = company.name if company else "PayrollOS"

    send_password_reset(user.email, token, company_name)
    return {"message": "If that email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(req: ResetRequest):
    user_id = await consume_reset_token(req.token)
    if not user_id:
        raise HTTPException(400, "Invalid or expired reset token")
    if len(req.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    user = await User.find_one(User.id == user_id)
    if not user:
        raise HTTPException(400, "User not found")

    user.password_hash = hash_password(req.new_password)
    await user.save()
    return {"message": "Password updated successfully"}


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest):
    raise HTTPException(501, "Use /auth/reset-password for now")
