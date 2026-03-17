"""
Leave management — track extended leave beyond PTO.
Covers: FMLA, parental leave, military leave, medical, personal.

Leave periods affect payroll (unpaid leave = 0 wages).
"""
import uuid
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, Date, DateTime, Integer, ForeignKey, Text, select, func
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

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


class LeaveRecord(Base):
    __tablename__ = "leave_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    leave_type = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    expected_return = Column(Date)
    actual_return = Column(Date)
    is_paid = Column(Boolean, default=False)
    status = Column(String(20), default="pending")  # pending|approved|active|completed|denied
    reason = Column(Text)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at = Column(DateTime(timezone=True))
    intermittent = Column(Boolean, default=False)   # FMLA intermittent leave
    documentation_received = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class LeaveCreate(BaseModel):
    employee_id: str
    leave_type: str
    start_date: date
    expected_return: Optional[date] = None
    is_paid: Optional[bool] = None   # None = use default for type
    reason: Optional[str] = None
    intermittent: bool = False
    documentation_received: bool = False


class LeaveReview(BaseModel):
    status: str   # approved | denied
    notes: Optional[str] = None


@router.get("/types")
async def list_leave_types():
    return [{"key": k, **v} for k, v in LEAVE_TYPES.items()]


@router.get("")
async def list_leave(
    employee_id: Optional[str] = None,
    status: Optional[str] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(LeaveRecord).where(LeaveRecord.company_id == current_user["company_id"])
    if employee_id:
        q = q.where(LeaveRecord.employee_id == employee_id)
    if status:
        q = q.where(LeaveRecord.status == status)
    if active_only:
        today = date.today()
        q = q.where(
            LeaveRecord.status.in_(["approved", "active"]),
            LeaveRecord.start_date <= today,
        )
    q = q.order_by(LeaveRecord.start_date.desc()).limit(200)
    result = await db.execute(q)
    records = result.scalars().all()
    return [_ser(r) for r in records]


@router.post("", status_code=201)
async def create_leave(
    body: LeaveCreate,
    db: AsyncSession = Depends(get_db),
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
        employee_id=body.employee_id,
        leave_type=body.leave_type,
        start_date=body.start_date,
        expected_return=expected_return,
        is_paid=is_paid,
        reason=body.reason,
        intermittent=body.intermittent,
        documentation_received=body.documentation_received,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _ser(record)


@router.put("/{leave_id}/review")
async def review_leave(
    leave_id: str,
    body: LeaveReview,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(LeaveRecord).where(
            LeaveRecord.id == leave_id,
            LeaveRecord.company_id == current_user["company_id"],
        )
    )
    record = result.scalar_one_or_none()
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
        record.notes = (record.notes or "") + f"\n{body.notes}"
    await db.commit()
    await db.refresh(record)
    return _ser(record)


@router.put("/{leave_id}/return")
async def record_return(
    leave_id: str,
    return_date: date,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Record employee's actual return from leave."""
    result = await db.execute(
        select(LeaveRecord).where(
            LeaveRecord.id == leave_id,
            LeaveRecord.company_id == current_user["company_id"],
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Leave record not found")
    record.actual_return = return_date
    record.status = "completed"
    await db.commit()
    return {"message": "Return recorded", "actual_return": str(return_date)}


@router.get("/active")
async def active_leave_today(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Employees currently on leave today."""
    today = date.today()
    result = await db.execute(
        select(LeaveRecord).where(
            LeaveRecord.company_id == current_user["company_id"],
            LeaveRecord.status.in_(["approved", "active"]),
            LeaveRecord.start_date <= today,
            (LeaveRecord.actual_return == None) | (LeaveRecord.actual_return > today),
        )
    )
    records = result.scalars().all()
    return {
        "date": str(today),
        "count": len(records),
        "employees_on_leave": [_ser(r) for r in records],
    }


@router.get("/calendar")
async def leave_calendar(
    month: int,
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """All leave in a given month."""
    from calendar import monthrange
    _, last_day = monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)

    result = await db.execute(
        select(LeaveRecord).where(
            LeaveRecord.company_id == current_user["company_id"],
            LeaveRecord.status.in_(["approved", "active", "completed"]),
            LeaveRecord.start_date <= month_end,
            (LeaveRecord.expected_return >= month_start) |
            (LeaveRecord.actual_return >= month_start) |
            (LeaveRecord.expected_return == None),
        ).order_by(LeaveRecord.start_date)
    )
    records = result.scalars().all()
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
