import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from models import LeaveRecord, Employee
from utils.auth import get_current_user
from uuid import UUID
from beanie.operators import In, Or

router = APIRouter(prefix="/leave", tags=["leave"])

LEAVE_TYPES = {
    "fmla":             {"paid": False, "max_weeks": 12, "label": "FMLA (Family & Medical)"},
    "parental":         {"paid": True,  "max_weeks": 12, "label": "Parental Leave"},
    "medical":          {"paid": False, "max_weeks": 26, "label": "Medical Leave"},
    "military":         {"paid": False, "max_weeks": 52, "label": "Military Leave (USERRA)"},
    "bereavement":      {"paid": True,  "max_weeks": 1,  "label": "Bereavement"},
    "personal":         {"paid": False, "max_weeks": 4,  "label": "Personal Leave"},
    "workers_comp":     {"paid": False, "max_weeks": 52, "label": "Workers' Compensation"},
    "jury_duty":        {"paid": True,  "max_weeks": 2,  "label": "Jury Duty"},
    "administrative":   {"paid": True,  "max_weeks": 4,  "label": "Administrative Leave"},
}


# ── Schemas ────────────────────────────────────────────────────
class LeaveCreate(BaseModel):
    employee_id: str
    leave_type: str
    start_date: date
    expected_return: Optional[date] = None
    is_paid: Optional[bool] = False
    reason: Optional[str] = None
    intermittent: bool = False
    documentation_received: bool = False

    @field_validator("expected_return", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

    @field_validator("is_paid", mode="before")
    @classmethod
    def handle_none_is_paid(cls, v):
        if v is None or v == "":
            return False
        return v


class LeaveReview(BaseModel):
    status: str   # approved|denied
    notes: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────
@router.get("/types")
async def list_leave_types():
    return [{"key": k, **v} for k, v in LEAVE_TYPES.items()]


@router.get("")
async def list_leave_records(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = UUID(employee_id)
    if status:
        query["status"] = status
    
    records = await LeaveRecord.find(query).sort("-created_at").to_list()
    out = []
    for r in records:
        emp = await Employee.find_one(Employee.id == r.employee_id)
        out.append({
            **_ser(r),
            "employee_name": f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
        })
    return out


@router.post("", status_code=201)
async def create_leave_record(
    body: LeaveCreate,
    current_user: dict = Depends(get_current_user),
):
    if body.leave_type not in LEAVE_TYPES:
        raise HTTPException(400, f"Invalid leave_type. Must be one of: {', '.join(LEAVE_TYPES)}")

    type_info = LEAVE_TYPES[body.leave_type]
    is_paid = body.is_paid if body.is_paid is not None else type_info["paid"]

    # Calculate expected return if not provided
    expected_return = body.expected_return
    if not expected_return and type_info.get("max_weeks"):
        expected_return = body.start_date + timedelta(weeks=type_info["max_weeks"])

    record = LeaveRecord(
        company_id=current_user["company_id"],
        employee_id=UUID(body.employee_id),
        leave_type=body.leave_type,
        start_date=body.start_date,
        expected_return=expected_return,
        is_paid=is_paid,
        reason=body.reason,
        intermittent=body.intermittent,
        documentation_received=body.documentation_received,
        status="pending",
    )
    await record.insert()
    return _ser(record)


@router.put("/{record_id}/review")
async def review_leave(
    record_id: str,
    body: LeaveReview,
    current_user: dict = Depends(get_current_user),
):
    record = await LeaveRecord.find_one(
        LeaveRecord.id == UUID(record_id),
        LeaveRecord.company_id == current_user["company_id"]
    )
    if not record:
        raise HTTPException(404, "Leave record not found")
    if record.status not in ("pending", "approved"):
        raise HTTPException(400, f"Cannot review a {record.status} leave")
    if body.status not in ("approved", "denied", "active", "completed"):
        raise HTTPException(400, "status must be: approved, denied, active, completed")

    record.status = body.status
    record.approved_by = current_user["sub"]
    record.approved_at = datetime.utcnow()
    if body.notes:
        record.notes = (record.notes or "") + f"\nReview note: {body.notes}"
    
    await record.save()
    return _ser(record)


@router.post("/{record_id}/return")
async def record_return(
    record_id: str,
    actual_return_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
):
    """Mark the employee as returned from leave."""
    record = await LeaveRecord.find_one(
        LeaveRecord.id == UUID(record_id),
        LeaveRecord.company_id == current_user["company_id"]
    )
    if not record:
        raise HTTPException(404, "Leave record not found")

    record.actual_return = actual_return_date or datetime.utcnow().date()
    record.status = "completed"
    await record.save()
    return {"message": "Return recorded", "date": str(record.actual_return)}


@router.get("/active")
async def active_leave_today(
    current_user: dict = Depends(get_current_user),
):
    """Employees currently on leave today."""
    today = date.today()
    records = await LeaveRecord.find(
        LeaveRecord.company_id == current_user["company_id"],
        In(LeaveRecord.status, ["approved", "active"]),
        LeaveRecord.start_date <= today,
        Or(LeaveRecord.actual_return == None, LeaveRecord.actual_return > today),
    ).to_list()
    return {
        "date": str(today),
        "count": len(records),
        "employees_on_leave": [_ser(r) for r in records],
    }


@router.get("/calendar")
async def leave_calendar(
    month: int,
    year: int,
    current_user: dict = Depends(get_current_user),
):
    """All leave in a given month."""
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    company_id = current_user["company_id"]
    
    records = await LeaveRecord.find(
        LeaveRecord.company_id == company_id,
        In(LeaveRecord.status, ["approved", "active", "completed"]),
        LeaveRecord.start_date <= month_end,
        Or(
            LeaveRecord.expected_return >= month_start,
            LeaveRecord.actual_return >= month_start,
            LeaveRecord.expected_return == None
        ),
    ).sort("start_date").to_list()

    return {
        "year": year, "month": month,
        "leave_events": [_ser(r) for r in records],
    }


def _ser(r: LeaveRecord) -> dict:
    type_info = LEAVE_TYPES.get(r.leave_type, {})
    days = None
    if r.start_date and r.expected_return:
        days = (r.expected_return - r.start_date).days
    return {
        "id": str(r.id),
        "employee_id": str(r.employee_id),
        "leave_type": r.leave_type,
        "leave_label": type_info.get("label", r.leave_type),
        "start_date": str(r.start_date),
        "expected_return": str(r.expected_return) if r.expected_return else None,
        "actual_return": str(r.actual_return) if r.actual_return else None,
        "duration_days": days,
        "is_paid": r.is_paid,
        "status": r.status,
        "reason": r.reason,
        "intermittent": r.intermittent,
        "documentation_received": r.documentation_received,
        "notes": r.notes,
        "approved_at": str(r.approved_at) if r.approved_at else None,
    }
