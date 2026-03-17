"""
Recurring payroll scheduler.
Runs payroll automatically on schedule using APScheduler (optional dependency).
Can also be triggered manually or via cron.

POST /scheduler/setup       configure auto-payroll
GET  /scheduler/status      next scheduled runs
POST /scheduler/trigger     manually trigger scheduled run
DELETE /scheduler/cancel    disable auto-payroll
"""
import uuid
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class ScheduleConfig(Base):
    __tablename__ = "payroll_schedules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), unique=True)
    frequency = Column(String(20), default="biweekly")
    next_period_start = Column(Date)
    next_run_date = Column(Date)
    auto_approve = Column(Boolean, default=False)   # if True, runs without manual approval
    notify_email = Column(String(255))
    is_active = Column(Boolean, default=False)
    last_run = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ScheduleCreate(BaseModel):
    frequency: str = "biweekly"
    first_period_start: date
    auto_approve: bool = False
    notify_email: Optional[str] = None


FREQ_DAYS = {"weekly": 7, "biweekly": 14, "semimonthly": 15, "monthly": 30}


def next_dates(start: date, frequency: str) -> tuple[date, date, date]:
    """Return (period_start, period_end, pay_date)."""
    days = FREQ_DAYS.get(frequency, 14)
    period_end = start + timedelta(days=days - 1)
    pay_date = period_end + timedelta(days=5)
    return start, period_end, pay_date


@router.get("/status")
async def get_schedule_status(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(ScheduleConfig).where(ScheduleConfig.company_id == current_user["company_id"])
    )
    config = result.scalar_one_or_none()
    if not config:
        return {"configured": False, "message": "No payroll schedule configured"}

    upcoming = []
    if config.is_active and config.next_period_start:
        run_start = config.next_period_start
        for i in range(4):  # next 4 runs
            s, e, p = next_dates(run_start + timedelta(days=FREQ_DAYS.get(config.frequency, 14) * i), config.frequency)
            if i == 0:
                s = config.next_period_start
                e = s + timedelta(days=FREQ_DAYS.get(config.frequency, 14) - 1)
                p = e + timedelta(days=5)
            upcoming.append({"period_start": str(s), "period_end": str(e), "pay_date": str(p)})

    return {
        "configured": True,
        "is_active": config.is_active,
        "frequency": config.frequency,
        "auto_approve": config.auto_approve,
        "notify_email": config.notify_email,
        "next_run": str(config.next_run_date) if config.next_run_date else None,
        "last_run": str(config.last_run) if config.last_run else None,
        "upcoming_runs": upcoming,
    }


@router.post("/setup", status_code=201)
async def setup_schedule(
    body: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin required")

    result = await db.execute(
        select(ScheduleConfig).where(ScheduleConfig.company_id == current_user["company_id"])
    )
    config = result.scalar_one_or_none()

    _, period_end, pay_date = next_dates(body.first_period_start, body.frequency)

    if config:
        config.frequency = body.frequency
        config.next_period_start = body.first_period_start
        config.next_run_date = pay_date - timedelta(days=2)  # run 2 days before pay date
        config.auto_approve = body.auto_approve
        config.notify_email = body.notify_email
        config.is_active = True
        config.updated_at = datetime.utcnow()
    else:
        config = ScheduleConfig(
            company_id=current_user["company_id"],
            frequency=body.frequency,
            next_period_start=body.first_period_start,
            next_run_date=pay_date - timedelta(days=2),
            auto_approve=body.auto_approve,
            notify_email=body.notify_email,
            is_active=True,
        )
        db.add(config)

    await db.commit()
    return {
        "message": "Payroll schedule configured",
        "frequency": config.frequency,
        "first_period_start": str(body.first_period_start),
        "auto_approve": config.auto_approve,
        "next_run_date": str(config.next_run_date),
    }


@router.post("/trigger")
async def trigger_payroll(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger the next scheduled payroll run."""
    result = await db.execute(
        select(ScheduleConfig).where(ScheduleConfig.company_id == current_user["company_id"])
    )
    config = result.scalar_one_or_none()
    if not config or not config.is_active:
        raise HTTPException(400, "No active payroll schedule")

    period_start = config.next_period_start
    _, period_end, pay_date = next_dates(period_start, config.frequency)

    # Run payroll
    from routes.payroll import run_payroll, PayrollRunRequest
    from fastapi import BackgroundTasks
    bt = BackgroundTasks()
    req = PayrollRunRequest(
        period_start=period_start,
        period_end=period_end,
        pay_date=pay_date,
        notes=f"Auto-scheduled run ({config.frequency})",
    )

    try:
        result_data = await run_payroll(req, bt, db, current_user)
    except Exception as e:
        raise HTTPException(500, f"Payroll run failed: {e}")

    # Advance to next period
    days = FREQ_DAYS.get(config.frequency, 14)
    config.next_period_start = period_start + timedelta(days=days)
    _, next_end, next_pay = next_dates(config.next_period_start, config.frequency)
    config.next_run_date = next_pay - timedelta(days=2)
    config.last_run = datetime.utcnow()
    await db.commit()

    return {
        "message": "Payroll run triggered",
        "pay_run_id": result_data.get("pay_run_id"),
        "period": f"{period_start} – {period_end}",
        "next_run_date": str(config.next_run_date),
    }


@router.delete("/cancel", status_code=204)
async def cancel_schedule(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(ScheduleConfig).where(ScheduleConfig.company_id == current_user["company_id"])
    )
    config = result.scalar_one_or_none()
    if config:
        config.is_active = False
        await db.commit()
