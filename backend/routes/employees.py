from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from beanie import operators
from pydantic import BaseModel
from datetime import date
from models import Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: date
    pay_type: str           # salary | hourly | contract
    pay_rate: float
    pay_frequency: str = "biweekly"
    department: Optional[str] = None
    job_title: Optional[str] = None
    filing_status: str = "single"
    federal_allowances: int = 0
    additional_federal_withholding: float = 0
    state_code: str = "NY"
    exempt_from_federal: bool = False
    exempt_from_state: bool = False
    health_insurance_deduction: float = 0
    dental_deduction: float = 0
    vision_deduction: float = 0
    retirement_401k_pct: float = 0
    hsa_deduction: float = 0
    garnishment_amount: float = 0
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None


class EmployeeUpdate(EmployeeCreate):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    hire_date: Optional[date] = None
    pay_type: Optional[str] = None
    pay_rate: Optional[float] = None
    status: Optional[str] = None


class TerminationRequest(BaseModel):
    termination_date: Optional[date] = None
    reason: Optional[str] = None


@router.get("")
async def list_employees(
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if status:
        query["status"] = status
    if department:
        query["department"] = department
    if search:
        # MongoDB regex search
        regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"first_name": regex},
            {"last_name": regex},
            {"email": regex}
        ]

    employees = await Employee.find(query).skip(skip).limit(limit).to_list()
    total = await Employee.find(query).count()

    return {
        "total": total,
        "employees": [_serialize(e) for e in employees],
    }


@router.post("", status_code=201)
async def create_employee(
    body: EmployeeCreate,
    current_user: dict = Depends(get_current_user),
):
    emp = Employee(company_id=current_user["company_id"], **body.model_dump())
    await emp.insert()
    return _serialize(emp)


@router.get("/{employee_id}")
async def get_employee(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    emp = await _get_or_404(employee_id, current_user["company_id"])
    return _serialize(emp)


@router.put("/{employee_id}")
async def update_employee(
    employee_id: UUID,
    body: EmployeeUpdate,
    current_user: dict = Depends(get_current_user),
):
    emp = await _get_or_404(employee_id, current_user["company_id"])
    update_data = body.model_dump(exclude_none=True)
    for k, v in update_data.items():
        setattr(emp, k, v)
    await emp.save()
    return _serialize(emp)


@router.delete("/{employee_id}", status_code=204)
async def delete_employee(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user),
):
    emp = await _get_or_404(employee_id, current_user["company_id"])
    emp.status = "terminated"
    emp.termination_date = date.today()
    await emp.save()


@router.post("/{employee_id}/terminate")
async def terminate_employee(
    employee_id: UUID,
    body: Optional[TerminationRequest] = None,
    current_user: dict = Depends(get_current_user),
):
    emp = await _get_or_404(employee_id, current_user["company_id"])
    emp.status = "terminated"
    emp.termination_date = (body.termination_date if body else None) or date.today()
    # If we had a reason field in the model, we would save it too.
    # Currently, Employee model doesn't have a termination_reason field.
    await emp.save()
    return _serialize(emp)


async def _get_or_404(employee_id, company_id):
    emp = await Employee.find_one(Employee.id == employee_id, Employee.company_id == company_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


def _serialize(e: Employee) -> dict:
    return {
        "id": str(e.id),
        "company_id": str(e.company_id),
        "first_name": e.first_name,
        "last_name": e.last_name,
        "full_name": f"{e.first_name} {e.last_name}",
        "email": e.email,
        "phone": e.phone,
        "hire_date": str(e.hire_date) if e.hire_date else None,
        "termination_date": str(e.termination_date) if e.termination_date else None,
        "status": e.status,
        "pay_type": e.pay_type,
        "pay_rate": float(e.pay_rate),
        "pay_frequency": e.pay_frequency,
        "department": e.department,
        "job_title": e.job_title,
        "filing_status": e.filing_status,
        "state_code": e.state_code,
        "health_insurance_deduction": float(e.health_insurance_deduction or 0),
        "dental_deduction": float(e.dental_deduction or 0),
        "vision_deduction": float(e.vision_deduction or 0),
        "retirement_401k_pct": float(e.retirement_401k_pct or 0),
        "hsa_deduction": float(e.hsa_deduction or 0),
        "garnishment_amount": float(e.garnishment_amount or 0),
        "additional_federal_withholding": float(e.additional_federal_withholding or 0),
        "exempt_from_federal": e.exempt_from_federal,
        "exempt_from_state": e.exempt_from_state,
        "address_line1": e.address_line1,
        "city": e.city,
        "state": e.state,
        "zip": e.zip,
        "created_at": str(e.created_at) if e.created_at else None,
    }
