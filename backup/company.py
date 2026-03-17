from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models import Company
from utils.auth import get_current_user

router = APIRouter(prefix="/company", tags=["company"])


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    ein: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    pay_frequency: Optional[str] = None


@router.get("")
async def get_company(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Company).where(Company.id == current_user["company_id"])
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Company not found")
    return _serialize(company)


@router.put("")
async def update_company(
    body: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Company).where(Company.id == current_user["company_id"])
    )
    company = result.scalar_one_or_none()
    if not company:
        raise HTTPException(404, "Company not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(company, k, v)
    await db.commit()
    await db.refresh(company)
    return _serialize(company)


def _serialize(c: Company) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "ein": c.ein,
        "address_line1": c.address_line1,
        "address_line2": c.address_line2,
        "city": c.city,
        "state": c.state,
        "zip": c.zip,
        "phone": c.phone,
        "email": c.email,
        "pay_frequency": c.pay_frequency,
        "created_at": str(c.created_at),
    }
