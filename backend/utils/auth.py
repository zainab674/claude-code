from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Depends, HTTPException, status, Query
from config import settings

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


import uuid

async def get_current_user(
    token: Optional[str] = Query(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    if not token and credentials:
        token = credentials.credentials
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
        
    payload = decode_token(token)
    
    # Cast known UUID fields to UUID objects for MongoDB compatibility
    if "company_id" in payload:
        try:
            payload["company_id"] = uuid.UUID(payload["company_id"])
        except (ValueError, TypeError):
            pass
            
    if "user_id" in payload:
        try:
            payload["user_id"] = uuid.UUID(payload["user_id"])
        except (ValueError, TypeError):
            pass

    if "sub" in payload:
        try:
            # Cast sub to UUID in place for consistency
            payload["sub"] = uuid.UUID(payload["sub"])
        except (ValueError, TypeError):
            pass
            
    return payload
