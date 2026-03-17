from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from database import get_db
from models import PayPeriod
from utils.auth import get_current_user

router = APIRouter(prefix="/pay-periods", tags=["pay-periods"])

FREQUENCY_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "semimonthly": 15,  # approximate
    "monthly": 30,
}


class PayPeriodCreate(BaseModel):
    period_start: date
    period_end: date
    pay_date: date


@router.get("")
async def list_pay_periods(
    status: Optional[str] = None,
    limit: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(PayPeriod).where(PayPeriod.company_id == current_user["company_id"])
    if status:
        q = q.where(PayPeriod.status == status)
    q = q.order_by(PayPeriod.period_start.desc()).limit(limit)
    result = await db.execute(q)
    periods = result.scalars().all()
    return [_serialize(p) for p in periods]


@router.post("", status_code=201)
async def create_pay_period(
    body: PayPeriodCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    period = PayPeriod(
        company_id=current_user["company_id"],
        period_start=body.period_start,
        period_end=body.period_end,
        pay_date=body.pay_date,
        status="open",
    )
    db.add(period)
    await db.commit()
    await db.refresh(period)
    return _serialize(period)


@router.post("/generate")
async def generate_pay_periods(
    frequency: str = "biweekly",
    start_date: Optional[date] = None,
    count: int = 26,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Auto-generate pay periods for the year."""
    if count > 52:
        raise HTTPException(400, "Maximum 52 periods at once")

    start = start_date or date(date.today().year, 1, 1)
    days = FREQUENCY_DAYS.get(frequency, 14)
    created = []

    for i in range(count):
        period_start = start + timedelta(days=days * i)
        period_end = period_start + timedelta(days=days - 1)
        pay_date = period_end + timedelta(days=5)

        # Check for duplicates
        existing = await db.execute(
            select(PayPeriod).where(
                PayPeriod.company_id == current_user["company_id"],
                PayPeriod.period_start == period_start,
            )
        )
        if existing.scalar_one_or_none():
            continue

        period = PayPeriod(
            company_id=current_user["company_id"],
            period_start=period_start,
            period_end=period_end,
            pay_date=pay_date,
            status="open",
        )
        db.add(period)
        created.append(period)

    await db.commit()
    return {"created": len(created), "frequency": frequency, "periods": [_serialize(p) for p in created]}


def _serialize(p: PayPeriod) -> dict:
    return {
        "id": str(p.id),
        "period_start": str(p.period_start),
        "period_end": str(p.period_end),
        "pay_date": str(p.pay_date),
        "status": p.status,
        "created_at": str(p.created_at),
    }
