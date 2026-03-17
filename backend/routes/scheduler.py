"""
Recurring payroll scheduler.
Runs payroll automatically on schedule using APScheduler (optional dependency).
Can also be triggered manually or via cron.

POST /scheduler/setup       configure auto-payroll
GET  /scheduler/status      next scheduled runs
POST /scheduler/trigger     manually trigger scheduled run
DELETE /scheduler/cancel    disable auto-payroll"""
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from models import ScheduleConfig
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class ScheduleCreate(BaseModel):
    frequency: str = "biweekly"
    first_period_start: date
    auto_approve: bool = False
    notify_email: Optional[str] = None


class ScheduleUpdate(BaseModel):
    frequency: str = "biweekly"    # weekly|biweekly|monthly
    next_period_start: date
    next_run_date: date
    auto_approve: bool = False
    notify_email: Optional[str] = None
    is_active: bool = True


FREQ_DAYS = {"weekly": 7, "biweekly": 14, "semimonthly": 15, "monthly": 30}


def next_dates(start: date, frequency: str) -> tuple[date, date, date]:
    """Return (period_start, period_end, pay_date)."""
    days = FREQ_DAYS.get(frequency, 14)
    period_end = start + timedelta(days=days - 1)
    pay_date = period_end + timedelta(days=5)
    return start, period_end, pay_date


@router.get("/status")
async def get_schedule_status(
    current_user: dict = Depends(get_current_user),
):
    config = await ScheduleConfig.find_one(ScheduleConfig.company_id == current_user["company_id"])
    if not config:
        return {"configured": False, "message": "No payroll schedule configured"}

    upcoming = []
    if config.is_active and config.next_period_start:
        run_start = config.next_period_start.date() if isinstance(config.next_period_start, datetime) else config.next_period_start
        for i in range(4):  # next 4 runs
            s, e, p = next_dates(run_start + timedelta(days=FREQ_DAYS.get(config.frequency, 14) * i), config.frequency)
            if i == 0:
                s = run_start
                e = s + timedelta(days=FREQ_DAYS.get(config.frequency, 14) - 1)
                p = e + timedelta(days=5)
            upcoming.append({"period_start": str(s), "period_end": str(e), "pay_date": str(p)})

    return {
        "configured": True,
        "is_active": config.is_active,
        "frequency": config.frequency,
        "auto_approve": config.auto_approve,
        "notify_email": config.notify_email,
        "next_run": str(config.next_run_date.date()) if config.next_run_date else None,
        "last_run": str(config.last_run) if config.last_run else None,
        "upcoming_runs": upcoming,
    }


@router.post("/setup", status_code=201)
async def setup_schedule(
    body: ScheduleCreate,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Admin required")

    company_id = current_user["company_id"]
    config = await ScheduleConfig.find_one(ScheduleConfig.company_id == company_id)

    _, period_end, pay_date = next_dates(body.first_period_start, body.frequency)

    if config:
        config.frequency = body.frequency
        config.next_period_start = datetime.combine(body.first_period_start, datetime.min.time())
        config.next_run_date = datetime.combine(pay_date - timedelta(days=2), datetime.min.time())
        config.auto_approve = body.auto_approve
        config.notify_email = body.notify_email
        config.is_active = True
        config.updated_at = datetime.utcnow()
    else:
        config = ScheduleConfig(
            company_id=company_id,
            frequency=body.frequency,
            next_period_start=datetime.combine(body.first_period_start, datetime.min.time()),
            next_run_date=datetime.combine(pay_date - timedelta(days=2), datetime.min.time()),
            auto_approve=body.auto_approve,
            notify_email=body.notify_email,
            is_active=True,
        )
        await config.insert()

    await config.save()
    return {
        "message": "Payroll schedule configured",
        "frequency": config.frequency,
        "first_period_start": str(body.first_period_start),
        "auto_approve": config.auto_approve,
        "next_run_date": str(config.next_run_date.date()) if config.next_run_date else None,
    }


@router.post("/trigger")
async def trigger_payroll(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger the next scheduled payroll run."""
    config = await ScheduleConfig.find_one(ScheduleConfig.company_id == current_user["company_id"])
    if not config or not config.is_active:
        raise HTTPException(400, "No active payroll schedule")

    period_start = config.next_period_start.date() if isinstance(config.next_period_start, datetime) else config.next_period_start
    _, period_end, pay_date = next_dates(period_start, config.frequency)

    # Run payroll
    from routes.payroll import run_payroll, PayrollRunRequest
    req = PayrollRunRequest(
        period_start=period_start,
        period_end=period_end,
        pay_date=pay_date,
        notes=f"Auto-scheduled run ({config.frequency})",
    )

    try:
        result_data = await run_payroll(req, background_tasks, current_user)
    except Exception as e:
        raise HTTPException(500, f"Payroll run failed: {e}")

    # Advance to next period
    days = FREQ_DAYS.get(config.frequency, 14)
    next_start = period_start + timedelta(days=days)
    config.next_period_start = datetime.combine(next_start, datetime.min.time())
    _, next_end, next_pay = next_dates(next_start, config.frequency)
    config.next_run_date = datetime.combine(next_pay - timedelta(days=2), datetime.min.time())
    config.last_run = datetime.utcnow()
    await config.save()

    return {
        "message": "Payroll run triggered",
        "pay_run_id": result_data.get("pay_run_id"),
        "period": f"{period_start} – {period_end}",
        "next_run_date": str(config.next_run_date.date()) if config.next_run_date else None,
    }


@router.delete("/cancel", status_code=204)
async def cancel_schedule(
    current_user: dict = Depends(get_current_user),
):
    config = await ScheduleConfig.find_one(ScheduleConfig.company_id == current_user["company_id"])
    if config:
        config.is_active = False
        await config.save()
