"""
Time tracking system.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
    notes: Optional[str] = None


class TimeEntryUpdate(BaseModel):
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    regular_hours: Optional[float] = None
    overtime_hours: Optional[float] = None
    status: Optional[str] = None # pending | approved | rejected
    notes: Optional[str] = None


@router.get("")
async def list_time_entries(
    employee_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = uuid.UUID(employee_id)
    if start_date:
        query["entry_date"] = {"$gte": start_date}
    if end_date:
        if "entry_date" in query:
            query["entry_date"]["$lte"] = end_date
        else:
            query["entry_date"] = {"$lte": end_date}
    if status:
        query["status"] = status
        
    entries = await TimeEntry.find(query).sort("-entry_date").limit(200).to_list()
    return [_serialize(e) for e in entries]


@router.post("", status_code=201)
async def create_time_entry(
    body: TimeEntryCreate,
    current_user: dict = Depends(get_current_user),
):
    # Auto-calculate hours from clock in/out if not provided
    regular_hours = body.regular_hours
    if body.clock_in and body.clock_out and regular_hours == 0:
        total_seconds = (body.clock_out - body.clock_in).total_seconds()
        total_hours = total_seconds / 3600
        regular_hours = min(total_hours, 8.0)
        overtime = max(total_hours - 8.0, 0.0)
    else:
        overtime = body.overtime_hours

    entry = TimeEntry(
        company_id=current_user["company_id"],
        employee_id=uuid.UUID(body.employee_id),
        entry_date=body.entry_date,
        clock_in=body.clock_in,
        clock_out=body.clock_out,
        regular_hours=regular_hours,
        overtime_hours=overtime,
        notes=body.notes,
    )
    await entry.insert()
    return _serialize(entry)


@router.put("/{entry_id}")
async def update_time_entry(
    entry_id: uuid.UUID,
    body: TimeEntryUpdate,
    current_user: dict = Depends(get_current_user),
):
    entry = await TimeEntry.find_one(
        TimeEntry.id == entry_id,
        TimeEntry.company_id == current_user["company_id"]
    )
    if not entry:
        raise HTTPException(404, "Time entry not found")
    
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(entry, k, v)
        
    await entry.save()
    return _serialize(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_time_entry(
    entry_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    entry = await TimeEntry.find_one(
        TimeEntry.id == entry_id,
        TimeEntry.company_id == current_user["company_id"]
    )
    if entry:
        await entry.delete()


@router.post("/{entry_id}/approve")
async def approve_time_entry(
    entry_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    entry = await TimeEntry.find_one(
        TimeEntry.id == entry_id,
        TimeEntry.company_id == current_user["company_id"]
    )
    if not entry:
        raise HTTPException(404, "Time entry not found")
        
    entry.status = "approved"
    await entry.save()
    return _serialize(entry)


@router.get("/summary")
async def time_summary(
    employee_id: str,
    start_date: date,
    end_date: date,
    current_user: dict = Depends(get_current_user),
):
    """Aggregate hours for an employee over a date range — used to prefill payroll run."""
    comp_id = current_user["company_id"]
    emp_id = uuid.UUID(employee_id)
    
    pipeline = [
        {"$match": {
            "company_id": comp_id,
            "employee_id": emp_id,
            "entry_date": {"$gte": datetime.combine(start_date, datetime.min.time()), 
                           "$lte": datetime.combine(end_date, datetime.max.time())}
        }},
        {"$group": {
            "_id": None,
            "regular": {"$sum": "$regular_hours"},
            "overtime": {"$sum": "$overtime_hours"}
        }}
    ]
    
    # We need to be careful with date comparison in aggregation
    # Beanie stores dates as ISODate (datetime)
    
    results = await TimeEntry.aggregate(pipeline).to_list()
    
    if not results:
        return {
            "employee_id": employee_id,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "regular_hours": 0.0,
            "overtime_hours": 0.0,
            "total_hours": 0.0,
        }
        
    row = results[0]
    reg = float(row.get("regular", 0))
    over = float(row.get("overtime", 0))
    
    return {
        "employee_id": employee_id,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "regular_hours": reg,
        "overtime_hours": over,
        "total_hours": reg + over,
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
        "status": e.status,
        "notes": e.notes,
        "created_at": str(e.created_at),
    }
