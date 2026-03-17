"""
Company profile and settings.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import Company
from utils.auth import get_current_user

router = APIRouter(prefix="/company", tags=["company"])


class CompanyUpdate(BaseModel):
    name: str
    ein: str
    address_line1: str
    city: str
    state: str
    zip: str
    email: str
    phone: str
    website: str


@router.get("")
async def get_company(current_user: dict = Depends(get_current_user)):
    company = await Company.get(current_user["company_id"])
    if not company:
        raise HTTPException(404, "Company not found")
    return _ser(company)


@router.put("")
async def update_company(
    body: CompanyUpdate,
    current_user: dict = Depends(get_current_user)
):
    company = await Company.get(current_user["company_id"])
    if not company:
        raise HTTPException(404, "Company not found")
    
    for k, v in body.model_dump().items():
        setattr(company, k, v)
    
    company.updated_at = datetime.utcnow()
    await company.save()
    return _ser(company)


def _ser(c: Company) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "ein": c.ein,
        "address_line1": c.address_line1,
        "city": c.city,
        "state": c.state,
        "zip": c.zip,
        "email": c.email,
        "phone": c.phone,
        "website": c.website,
        "created_at": str(c.created_at),
    }
