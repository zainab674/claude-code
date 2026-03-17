from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from models import Employee
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/org-chart", tags=["org-chart"])


@router.get("")
async def get_org_chart(
    current_user: dict = Depends(get_current_user),
):
    """Return the full org chart as a nested tree."""
    company_id = current_user["company_id"]
    employees = await Employee.find(
        Employee.company_id == company_id,
        Employee.status == "active",
    ).to_list()

    # Build lookup and children map
    emp_map = {str(e.id): e for e in employees}
    children_map: dict = {str(e.id): [] for e in employees}
    roots = []

    for emp in employees:
        manager_id = str(emp.manager_id) if emp.manager_id else None
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
    current_user: dict = Depends(get_current_user),
):
    """Flat list of employees with their manager info."""
    query = {
        "company_id": current_user["company_id"],
        "status": "active",
    }
    if department:
        query["department"] = department
        
    employees = await Employee.find(query).to_list()
    emp_map = {str(e.id): f"{e.first_name} {e.last_name}" for e in employees}

    return [
        {
            "id": str(e.id),
            "name": f"{e.first_name} {e.last_name}",
            "job_title": e.job_title,
            "department": e.department,
            "manager_id": str(e.manager_id) if e.manager_id else None,
            "manager_name": emp_map.get(str(e.manager_id)) if e.manager_id else None,
        }
        for e in employees
    ]


@router.put("/employee/{employee_id}/manager")
async def set_manager(
    employee_id: str,
    manager_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Set or clear the manager for an employee."""
    emp_uuid = UUID(employee_id)
    company_id = current_user["company_id"]
    
    emp = await Employee.find_one(Employee.id == emp_uuid, Employee.company_id == company_id)
    if not emp:
        raise HTTPException(404, "Employee not found")

    if manager_id:
        mgr_uuid = UUID(manager_id)
        # Verify manager exists and belongs to same company
        mgr = await Employee.find_one(Employee.id == mgr_uuid, Employee.company_id == company_id)
        if not mgr:
            raise HTTPException(400, "Manager not found in this company")
        if mgr_uuid == emp_uuid:
            raise HTTPException(400, "Employee cannot be their own manager")
        emp.manager_id = mgr_uuid
    else:
        emp.manager_id = None

    await emp.save()
    return {"message": "Manager updated", "employee_id": employee_id, "manager_id": manager_id}


@router.get("/stats")
async def org_stats(
    current_user: dict = Depends(get_current_user),
):
    """Headcount and span-of-control statistics."""
    company_id = current_user["company_id"]
    
    # Use MongoDB aggregation for stats
    pipeline_dept = [
        {"$match": {"company_id": company_id, "status": "active"}},
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    by_dept = await Employee.aggregate(pipeline_dept).to_list()

    total = await Employee.find(Employee.company_id == company_id, Employee.status == "active").count()

    pipeline_type = [
        {"$match": {"company_id": company_id, "status": "active"}},
        {"$group": {"_id": "$pay_type", "count": {"$sum": 1}}}
    ]
    by_type = await Employee.aggregate(pipeline_type).to_list()

    return {
        "total_headcount": total,
        "by_department": [{"department": r["_id"] or "Unassigned", "count": r["count"]} for r in by_dept],
        "by_pay_type": [{"pay_type": r["_id"], "count": r["count"]} for r in by_type],
    }
