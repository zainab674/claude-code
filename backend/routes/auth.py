from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from models import User, Company
from utils.auth import hash_password, verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    company_name: str
    email: str
    password: str
    first_name: str
    last_name: str


@router.post("/login")
async def login(req: LoginRequest):
    user = await User.find_one(User.email == req.email)
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id),
        "role": user.role,
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "company_id": str(user.company_id),
        }
    }


@router.post("/register")
async def register(req: RegisterRequest):
    existing = await User.find_one(User.email == req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    
    company = Company(name=req.company_name)
    await company.insert()
    
    user = User(
        company_id=company.id,
        email=req.email,
        password_hash=hash_password(req.password),
        first_name=req.first_name,
        last_name=req.last_name,
        role="admin",
    )
    await user.insert()
    
    token = create_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(company.id),
        "role": "admin",
    })
    return {"access_token": token, "token_type": "bearer"}
