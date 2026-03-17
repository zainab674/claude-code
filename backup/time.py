from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from database import get_db
from models import TimeEntry, Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/time", tags=["time"])


class TimeEntryCreate(BaseModel):
    employee_id: str
    entry_date: date
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    regular_hours: float = 0.0
    overtime_hours: float = 0.0
    entry_type: str = "work"
    notes: Optional[str] = None


class TimeEntryUpdate(BaseModel):
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    regular_hours: Optional[float] = None
    overtime_hours: Optional[float] = None
    entry_type: Optional[str] = None
    notes: Optional[str] = None
    approved: Optional[bool] = None


@router.get("")
async def list_time_entries(
    employee_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    approved: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(TimeEntry).where(TimeEntry.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(TimeEntry.employee_id == employee_id)
    if start_date:
        q = q.where(TimeEntry.entry_date >= start_date)
    if end_date:
        q = q.where(TimeEntry.entry_date <= end_date)
    if approved is not None:
        q = q.where(TimeEntry.approved == approved)
    q = q.order_by(TimeEntry.entry_date.desc()).limit(200)
    result = await db.execute(q)
    entries = result.scalars().all()
    return [_serialize(e) for e in entries]


@router.post("", status_code=201)
async def create_time_entry(
    body: TimeEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Auto-calculate hours from clock in/out if not provided
    regular_hours = body.regular_hours
    if body.clock_in and body.clock_out and regular_hours == 0:
        total_hours = (body.clock_out - body.clock_in).seconds / 3600
        regular_hours = min(total_hours, 8.0)
        overtime = max(total_hours - 8.0, 0.0)
    else:
        overtime = body.overtime_hours

    entry = TimeEntry(
        company_id=current_user["company_id"],
        employee_id=body.employee_id,
        entry_date=body.entry_date,
        clock_in=body.clock_in,
        clock_out=body.clock_out,
        regular_hours=regular_hours,
        overtime_hours=overtime,
        entry_type=body.entry_type,
        notes=body.notes,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _serialize(entry)


@router.put("/{entry_id}")
async def update_time_entry(
    entry_id: UUID,
    body: TimeEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(TimeEntry).where(TimeEntry.id == entry_id,
                                TimeEntry.company_id == current_user["company_id"])
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Time entry not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(entry, k, v)
    await db.commit()
    await db.refresh(entry)
    return _serialize(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_time_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(TimeEntry).where(TimeEntry.id == entry_id,
                                TimeEntry.company_id == current_user["company_id"])
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Time entry not found")
    await db.delete(entry)
    await db.commit()


@router.get("/summary")
async def time_summary(
    employee_id: str,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Aggregate hours for an employee over a date range — used to prefill payroll run."""
    result = await db.execute(
        select(
            func.sum(TimeEntry.regular_hours).label("regular"),
            func.sum(TimeEntry.overtime_hours).label("overtime"),
        ).where(
            TimeEntry.company_id == current_user["company_id"],
            TimeEntry.employee_id == employee_id,
            TimeEntry.entry_date >= start_date,
            TimeEntry.entry_date <= end_date,
        )
    )
    row = result.first()
    return {
        "employee_id": employee_id,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "regular_hours": float(row.regular or 0),
        "overtime_hours": float(row.overtime or 0),
        "total_hours": float((row.regular or 0) + (row.overtime or 0)),
    }


def _serialize(e: TimeEntry) -> dict:
    return {
        "id": str(e.id),
        "employee_id": str(e.employee_id),
        "entry_date": str(e.entry_date),
        "clock_in": str(e.clock_in) if e.clock_in else None,
        "clock_out": str(e.clock_out) if e.clock_out else None,
        "regular_hours": float(e.regular_hours or 0),
        "overtime_hours": float(e.overtime_hours or 0),
        "entry_type": e.entry_type,
        "notes": e.notes,
        "approved": e.approved,
        "created_at": str(e.created_at),
    }
