from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if status:
        query["status"] = status
    
    periods = await PayPeriod.find(query).sort("-period_start").limit(limit).to_list()
    return [_serialize(p) for p in periods]


@router.post("", status_code=201)
async def create_pay_period(
    body: PayPeriodCreate,
    current_user: dict = Depends(get_current_user),
):
    period = PayPeriod(
        company_id=current_user["company_id"],
        period_start=body.period_start,
        period_end=body.period_end,
        pay_date=body.pay_date,
        status="open",
    )
    await period.insert()
    return _serialize(period)


@router.post("/generate")
async def generate_pay_periods(
    frequency: str = "biweekly",
    start_date: Optional[date] = None,
    count: int = 26,
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

        # Check for duplicates using Beanie find_one
        existing = await PayPeriod.find_one(
            PayPeriod.company_id == current_user["company_id"],
            PayPeriod.period_start == period_start,
        )
        if existing:
            continue

        period = PayPeriod(
            company_id=current_user["company_id"],
            period_start=period_start,
            period_end=period_end,
            pay_date=pay_date,
            status="open",
        )
        await period.insert()
        created.append(period)

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
