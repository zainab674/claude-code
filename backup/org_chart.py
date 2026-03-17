"""
Org chart — employee reporting structure.
Employees have an optional manager_id field.
GET /org-chart              full tree from the top
GET /org-chart/employee/{id} subtree for one employee
PUT /org-chart/employee/{id} set manager
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID
from database import get_db
from models import Employee
from utils.auth import get_current_user

router = APIRouter(prefix="/org-chart", tags=["org-chart"])


@router.get("")
async def get_org_chart(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return the full org chart as a nested tree."""
    result = await db.execute(
        select(Employee).where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
    )
    employees = result.scalars().all()

    # Build lookup and children map
    emp_map = {str(e.id): e for e in employees}
    children_map: dict = {str(e.id): [] for e in employees}
    roots = []

    for emp in employees:
        manager_id = str(emp.manager_id) if hasattr(emp, 'manager_id') and emp.manager_id else None
        if manager_id and manager_id in emp_map:
            children_map[manager_id].append(str(emp.id))
        else:
            roots.append(str(emp.id))

    def build_node(emp_id: str, depth: int = 0) -> dict:
        emp = emp_map[emp_id]
        return {
            "id": str(emp.id),
            "name": f"{emp.first_name} {emp.last_name}",
            "job_title": emp.job_title,
            "department": emp.department,
            "email": emp.email,
            "pay_type": emp.pay_type,
            "depth": depth,
            "children": [build_node(cid, depth + 1) for cid in children_map.get(emp_id, [])],
            "direct_reports": len(children_map.get(emp_id, [])),
        }

    tree = [build_node(rid) for rid in roots]

    return {
        "total_employees": len(employees),
        "departments": sorted(list({e.department for e in employees if e.department})),
        "tree": tree,
    }


@router.get("/flat")
async def get_org_flat(
    department: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Flat list of employees with their manager info."""
    q = select(Employee).where(
        Employee.company_id == current_user["company_id"],
        Employee.status == "active",
    )
    if department:
        q = q.where(Employee.department == department)
    result = await db.execute(q)
    employees = result.scalars().all()
    emp_map = {str(e.id): f"{e.first_name} {e.last_name}" for e in employees}

    return [
        {
            "id": str(e.id),
            "name": f"{e.first_name} {e.last_name}",
            "job_title": e.job_title,
            "department": e.department,
            "manager_id": str(e.manager_id) if hasattr(e, 'manager_id') and e.manager_id else None,
            "manager_name": emp_map.get(str(e.manager_id)) if hasattr(e, 'manager_id') and e.manager_id else None,
        }
        for e in employees
    ]


@router.put("/employee/{employee_id}/manager")
async def set_manager(
    employee_id: str,
    manager_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Set or clear the manager for an employee."""
    result = await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.company_id == current_user["company_id"],
        )
    )
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "Employee not found")

    if manager_id:
        # Verify manager exists and belongs to same company
        mgr_result = await db.execute(
            select(Employee).where(
                Employee.id == manager_id,
                Employee.company_id == current_user["company_id"],
            )
        )
        mgr = mgr_result.scalar_one_or_none()
        if not mgr:
            raise HTTPException(400, "Manager not found in this company")
        if manager_id == employee_id:
            raise HTTPException(400, "Employee cannot be their own manager")

    if hasattr(emp, 'manager_id'):
        emp.manager_id = manager_id
    await db.commit()
    return {"message": "Manager updated", "employee_id": employee_id, "manager_id": manager_id}


@router.get("/stats")
async def org_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Headcount and span-of-control statistics."""
    from sqlalchemy import func
    result = await db.execute(
        select(
            Employee.department,
            func.count(Employee.id).label("count"),
        )
        .where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
        .group_by(Employee.department)
        .order_by(func.count(Employee.id).desc())
    )
    by_dept = result.all()

    total_res = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
    )
    total = total_res.scalar() or 0

    salary_res = await db.execute(
        select(
            Employee.pay_type,
            func.count(Employee.id).label("count"),
        )
        .where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
        .group_by(Employee.pay_type)
    )
    by_type = salary_res.all()

    return {
        "total_headcount": total,
        "by_department": [{"department": r.department or "Unassigned", "count": r.count} for r in by_dept],
        "by_pay_type": [{"pay_type": r.pay_type, "count": r.count} for r in by_type],
    }
