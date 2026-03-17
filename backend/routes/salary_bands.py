"""
Salary bands — compensation ranges by job level and department.
Migrated to Beanie (MongoDB).
"""
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import Employee, SalaryBand
from utils.auth import get_current_user

router = APIRouter(prefix="/salary-bands", tags=["salary-bands"])


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
    current_user: dict = Depends(get_current_user),
):
    query = {
        "company_id": current_user["company_id"],
        "is_active": True,
    }
    if department:
        query["department"] = department
    
    bands = await SalaryBand.find(query).sort("department", "min_salary").to_list()
    return [_ser(b) for b in bands]


@router.post("", status_code=201)
async def create_band(
    body: BandCreate,
    current_user: dict = Depends(get_current_user),
):
    if body.max_salary <= body.min_salary:
        raise HTTPException(400, "max_salary must be greater than min_salary")
    
    band = SalaryBand(
        company_id=current_user["company_id"],
        **body.model_dump(),
        effective_year=body.effective_year or datetime.utcnow().year,
    )
    await band.insert()
    return _ser(band)


@router.put("/{band_id}")
async def update_band(
    band_id: uuid.UUID,
    body: BandCreate,
    current_user: dict = Depends(get_current_user),
):
    band = await SalaryBand.find_one(
        SalaryBand.id == band_id,
        SalaryBand.company_id == current_user["company_id"]
    )
    if not band:
        raise HTTPException(404, "Band not found")
    
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(band, k, v)
    
    band.updated_at = datetime.utcnow()
    await band.save()
    return _ser(band)


@router.delete("/{band_id}", status_code=204)
async def delete_band(
    band_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    band = await SalaryBand.find_one(
        SalaryBand.id == band_id,
        SalaryBand.company_id == current_user["company_id"]
    )
    if not band:
        raise HTTPException(404, "Band not found")
    
    band.is_active = False
    await band.save()


@router.get("/analysis")
async def pay_equity_analysis(
    department: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Compare every employee's pay rate to their salary band."""
    emp_query = {
        "company_id": current_user["company_id"],
        "status": "active",
        "pay_type": "salary"
    }
    if department:
        emp_query["department"] = department
    
    employees = await Employee.find(emp_query).to_list()

    band_query = {
        "company_id": current_user["company_id"],
        "is_active": True
    }
    bands = await SalaryBand.find(band_query).to_list()

    # Index bands by department + job_title
    band_index = {}
    for b in bands:
        key = f"{b.department}:{b.job_title}"
        band_index[key] = b
        if b.job_title:
            band_index[f":{b.job_title}"] = b
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
            mid = float(band.mid_salary or (band.min_salary + band.max_salary) / 2)
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
    min_val = float(b.min_salary)
    max_val = float(b.max_salary)
    mid = float(b.mid_salary) if b.mid_salary else round((min_val + max_val) / 2, 2)
    return {
        "id": str(b.id),
        "job_title": b.job_title, 
        "department": b.department, 
        "level": b.level,
        "min_salary": min_val, 
        "mid_salary": mid,
        "max_salary": max_val,
        "range_spread": round((max_val - min_val) / min_val * 100, 1) if min_val else 0,
        "currency": b.currency, 
        "effective_year": b.effective_year,
        "notes": b.notes, 
        "is_active": b.is_active,
    }
