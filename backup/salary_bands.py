"""
Salary bands — compensation ranges by job level and department.
Used for pay equity analysis and offer letter generation.

POST /salary-bands           create band
GET  /salary-bands           list all bands
GET  /salary-bands/analysis  compare employees to their bands
PUT  /salary-bands/{id}      update band
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Integer, Boolean, select, func
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from models import Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/salary-bands", tags=["salary-bands"])


class SalaryBand(Base):
    __tablename__ = "salary_bands"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    job_title = Column(String(150))          # match to Employee.job_title
    department = Column(String(100))
    level = Column(String(50))               # IC1, IC2, Senior, Staff, Principal, etc.
    min_salary = Column(Numeric(12, 2), nullable=False)
    mid_salary = Column(Numeric(12, 2))      # midpoint / market rate
    max_salary = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="USD")
    effective_year = Column(Integer, default=lambda: datetime.utcnow().year)
    notes = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class BandCreate(BaseModel):
    job_title: Optional[str] = None
    department: Optional[str] = None
    level: Optional[str] = None
    min_salary: float
    mid_salary: Optional[float] = None
    max_salary: float
    currency: str = "USD"
    effective_year: Optional[int] = None
    notes: Optional[str] = None


@router.get("")
async def list_bands(
    department: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(SalaryBand).where(
        SalaryBand.company_id == current_user["company_id"],
        SalaryBand.is_active == True,
    )
    if department:
        q = q.where(SalaryBand.department == department)
    q = q.order_by(SalaryBand.department, SalaryBand.min_salary)
    result = await db.execute(q)
    return [_ser(b) for b in result.scalars().all()]


@router.post("", status_code=201)
async def create_band(
    body: BandCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.max_salary <= body.min_salary:
        raise HTTPException(400, "max_salary must be greater than min_salary")
    band = SalaryBand(
        company_id=current_user["company_id"],
        **body.model_dump(),
        effective_year=body.effective_year or datetime.utcnow().year,
    )
    db.add(band)
    await db.commit()
    await db.refresh(band)
    return _ser(band)


@router.put("/{band_id}")
async def update_band(
    band_id: str,
    body: BandCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(SalaryBand).where(
            SalaryBand.id == band_id,
            SalaryBand.company_id == current_user["company_id"],
        )
    )
    band = result.scalar_one_or_none()
    if not band:
        raise HTTPException(404, "Band not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(band, k, v)
    band.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(band)
    return _ser(band)


@router.delete("/{band_id}", status_code=204)
async def delete_band(
    band_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(SalaryBand).where(
            SalaryBand.id == band_id,
            SalaryBand.company_id == current_user["company_id"],
        )
    )
    band = result.scalar_one_or_none()
    if not band:
        raise HTTPException(404, "Band not found")
    band.is_active = False
    await db.commit()


@router.get("/analysis")
async def pay_equity_analysis(
    department: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Compare every employee's pay rate to their salary band."""
    emp_q = select(Employee).where(
        Employee.company_id == current_user["company_id"],
        Employee.status == "active",
        Employee.pay_type == "salary",
    )
    if department:
        emp_q = emp_q.where(Employee.department == department)
    emp_result = await db.execute(emp_q)
    employees = emp_result.scalars().all()

    band_result = await db.execute(
        select(SalaryBand).where(
            SalaryBand.company_id == current_user["company_id"],
            SalaryBand.is_active == True,
        )
    )
    bands = band_result.scalars().all()

    # Index bands by department + job_title
    band_index: dict = {}
    for b in bands:
        key = f"{b.department}:{b.job_title}"
        band_index[key] = b
        # Also index by just job_title
        if b.job_title:
            band_index[f":{b.job_title}"] = b
        # Index by just department
        if b.department:
            band_index[f"{b.department}:"] = b

    results = []
    below_band = at_band = above_band = no_band = 0

    for emp in employees:
        key = f"{emp.department}:{emp.job_title}"
        band = (band_index.get(key)
                or band_index.get(f":{emp.job_title}")
                or band_index.get(f"{emp.department}:"))

        salary = float(emp.pay_rate)
        if not band:
            no_band += 1
            position = "no_band"
            compa_ratio = None
        else:
            mid = float(band.mid_salary or (float(band.min_salary) + float(band.max_salary)) / 2)
            compa_ratio = round(salary / mid * 100, 1) if mid else None
            if salary < float(band.min_salary):
                position = "below_band"
                below_band += 1
            elif salary > float(band.max_salary):
                position = "above_band"
                above_band += 1
            else:
                position = "in_band"
                at_band += 1

        results.append({
            "employee_id": str(emp.id),
            "name": f"{emp.first_name} {emp.last_name}",
            "department": emp.department,
            "job_title": emp.job_title,
            "salary": salary,
            "band_min": float(band.min_salary) if band else None,
            "band_mid": float(band.mid_salary) if band and band.mid_salary else None,
            "band_max": float(band.max_salary) if band else None,
            "position": position,
            "compa_ratio": compa_ratio,
        })

    total = len(results)
    return {
        "total_employees": total,
        "in_band": at_band,
        "below_band": below_band,
        "above_band": above_band,
        "no_band_defined": no_band,
        "in_band_pct": round(at_band / total * 100, 1) if total else 0,
        "employees": sorted(results, key=lambda x: x["position"]),
    }


def _ser(b: SalaryBand) -> dict:
    mid = float(b.mid_salary) if b.mid_salary else round((float(b.min_salary) + float(b.max_salary)) / 2, 2)
    return {
        "id": str(b.id),
        "job_title": b.job_title, "department": b.department, "level": b.level,
        "min_salary": float(b.min_salary), "mid_salary": mid,
        "max_salary": float(b.max_salary),
        "range_spread": round((float(b.max_salary) - float(b.min_salary)) / float(b.min_salary) * 100, 1),
        "currency": b.currency, "effective_year": b.effective_year,
        "notes": b.notes, "is_active": b.is_active,
    }
