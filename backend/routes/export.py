import csv
import io
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Response
from models import Employee, PayRun, PayRunItem, PayPeriod, TimeEntry
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/export", tags=["export"])


def csv_response(rows: List[dict], filename: str) -> Response:
    """Build a CSV Response from a list of dicts."""
    if not rows:
        return Response(content="No data\n", media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/employees")
async def export_employees(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if status:
        query["status"] = status
    
    employees = await Employee.find(query).sort("last_name", "first_name").to_list()

    rows = [
        {
            "employee_id": str(e.id),
            "first_name": e.first_name,
            "last_name": e.last_name,
            "email": e.email or "",
            "phone": e.phone or "",
            "hire_date": str(e.hire_date) if e.hire_date else "",
            "status": e.status,
            "pay_type": e.pay_type,
            "pay_rate": float(e.pay_rate or 0),
            "pay_frequency": e.pay_frequency,
            "department": e.department or "",
            "job_title": e.job_title or "",
            "filing_status": e.filing_status,
            "state_code": e.state_code or "",
            "health_insurance_deduction": float(e.health_insurance_deduction or 0),
            "dental_deduction": float(e.dental_deduction or 0),
            "vision_deduction": float(e.vision_deduction or 0),
            "retirement_401k_pct": float(e.retirement_401k_pct or 0),
            "hsa_deduction": float(e.hsa_deduction or 0),
        }
        for e in employees
    ]
    return csv_response(rows, "employees.csv")


@router.get("/payroll-history")
async def export_payroll_history(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    company_id = current_user["company_id"]
    
    # We need to join PayRun and PayPeriod
    # In Beanie, we can use aggregation or manual join
    runs = await PayRun.find(PayRun.company_id == company_id).to_list()
    
    out = []
    for r in runs:
        period = await PayPeriod.find_one(PayPeriod.id == r.pay_period_id)
        if not period:
            continue
        
        if year and period.period_start.year != year:
            continue
            
        out.append({
            "pay_run_id": str(r.id),
            "period_start": str(period.period_start),
            "period_end": str(period.period_end),
            "pay_date": str(period.pay_date),
            "status": r.status,
            "employee_count": r.employee_count or 0,
            "total_gross": float(r.total_gross or 0),
            "total_employee_taxes": float(r.total_employee_taxes or 0),
            "total_employer_taxes": float(r.total_employer_taxes or 0),
            "total_deductions": float(r.total_deductions or 0),
            "total_net": float(r.total_net or 0),
            "created_at": str(r.created_at),
        })
    
    # Sort by start date desc
    out.sort(key=lambda x: x["period_start"], reverse=True)
    
    fname = f"payroll-history-{year or 'all'}.csv"
    return csv_response(out, fname)


@router.get("/employee-ytd")
async def export_employee_ytd(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    year = year or date.today().year
    company_id = current_user["company_id"]

    # Aggregate PayRunItems for completed runs in the target year
    pipeline = [
        {
            "$lookup": {
                "from": "pay_runs",
                "localField": "pay_run_id",
                "foreignField": "_id",
                "as": "run"
            }
        },
        {"$unwind": "$run"},
        {"$match": {"run.company_id": company_id, "run.status": "completed"}},
        {
            "$lookup": {
                "from": "pay_periods",
                "localField": "run.pay_period_id",
                "foreignField": "_id",
                "as": "period"
            }
        },
        {"$unwind": "$period"},
        {
            "$match": {
                "period.period_start": {
                    "$gte": datetime(year, 1, 1),
                    "$lte": datetime(year, 12, 31, 23, 59, 59)
                }
            }
        },
        {
            "$group": {
                "_id": "$employee_id",
                "ytd_gross": {"$sum": "$gross_pay"},
                "ytd_federal": {"$sum": "$federal_income_tax"},
                "ytd_state": {"$sum": "$state_income_tax"},
                "ytd_ss": {"$sum": "$social_security_tax"},
                "ytd_medicare": {"$sum": "$medicare_tax"},
                "ytd_add_medicare": {"$sum": "$additional_medicare_tax"},
                "ytd_401k": {"$sum": "$retirement_401k"},
                "ytd_health": {"$sum": "$health_insurance"},
                "ytd_dental": {"$sum": "$dental_insurance"},
                "ytd_vision": {"$sum": "$vision_insurance"},
                "ytd_hsa": {"$sum": "$hsa"},
                "ytd_garnishment": {"$sum": "$garnishment"},
                "ytd_net": {"$sum": "$net_pay"},
            }
        }
    ]
    
    ytd_stats = await PayRunItem.aggregate(pipeline).to_list()
    
    rows = []
    for stat in ytd_stats:
        emp = await Employee.find_one(Employee.id == stat["_id"])
        if not emp:
            continue
            
        rows.append({
            "employee_id": str(emp.id),
            "last_name": emp.last_name,
            "first_name": emp.first_name,
            "department": emp.department or "",
            "job_title": emp.job_title or "",
            "state": emp.state_code or "",
            "filing_status": emp.filing_status or "",
            "ytd_gross": round(float(stat["ytd_gross"] or 0), 2),
            "ytd_federal_income_tax": round(float(stat["ytd_federal"] or 0), 2),
            "ytd_state_income_tax": round(float(stat["ytd_state"] or 0), 2),
            "ytd_social_security": round(float(stat["ytd_ss"] or 0), 2),
            "ytd_medicare": round(float(stat["ytd_medicare"] or 0), 2),
            "ytd_additional_medicare": round(float(stat["ytd_add_medicare"] or 0), 2),
            "ytd_401k": round(float(stat["ytd_401k"] or 0), 2),
            "ytd_health_insurance": round(float(stat["ytd_health"] or 0), 2),
            "ytd_dental": round(float(stat["ytd_dental"] or 0), 2),
            "ytd_vision": round(float(stat["ytd_vision"] or 0), 2),
            "ytd_hsa": round(float(stat["ytd_hsa"] or 0), 2),
            "ytd_garnishment": round(float(stat["ytd_garnishment"] or 0), 2),
            "ytd_net": round(float(stat["ytd_net"] or 0), 2),
        })
    
    rows.sort(key=lambda x: (x["last_name"], x["first_name"]))
    return csv_response(rows, f"employee-ytd-{year}.csv")


@router.get("/pay-run/{run_id}")
async def export_pay_run_detail(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    run_uuid = UUID(run_id)
    company_id = current_user["company_id"]
    
    items = await PayRunItem.find(
        PayRunItem.pay_run_id == run_uuid,
        PayRunItem.company_id == company_id
    ).to_list()
    
    rows = []
    for i in items:
        emp = await Employee.find_one(Employee.id == i.employee_id)
        if not emp:
            continue
            
        rows.append({
            "last_name": emp.last_name,
            "first_name": emp.first_name,
            "department": emp.department or "",
            "job_title": emp.job_title or "",
            "pay_type": emp.pay_type,
            "regular_hours": float(i.regular_hours or 0),
            "overtime_hours": float(i.overtime_hours or 0),
            "regular_pay": float(i.regular_pay or 0),
            "overtime_pay": float(i.overtime_pay or 0),
            "bonus_pay": float(i.bonus_pay or 0),
            "gross_pay": float(i.gross_pay or 0),
            "health_insurance": float(i.health_insurance or 0),
            "retirement_401k": float(i.retirement_401k or 0),
            "total_pretax_deductions": float(i.total_pretax_deductions or 0),
            "federal_income_tax": float(i.federal_income_tax or 0),
            "state_income_tax": float(i.state_income_tax or 0),
            "social_security_tax": float(i.social_security_tax or 0),
            "medicare_tax": float(i.medicare_tax or 0),
            "total_employee_taxes": float(i.total_employee_taxes or 0),
            "employer_social_security": float(i.employer_social_security or 0),
            "employer_medicare": float(i.employer_medicare or 0),
            "futa_tax": float(i.futa_tax or 0),
            "total_employer_taxes": float(i.total_employer_taxes or 0),
            "garnishment": float(i.garnishment or 0),
            "net_pay": float(i.net_pay or 0),
            "ytd_gross": float(i.ytd_gross or 0),
            "ytd_net": float(i.ytd_net or 0),
        })
    
    rows.sort(key=lambda x: (x["last_name"], x["first_name"]))
    return csv_response(rows, f"pay-run-{run_id[:8]}.csv")


@router.get("/time-entries")
async def export_time_entries(
    employee_id: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if employee_id:
        query["employee_id"] = UUID(employee_id)
    
    # Date range query
    date_query = {}
    if start_date:
        date_query["$gte"] = start_date
    if end_date:
        date_query["$lte"] = end_date
    if date_query:
        query["entry_date"] = date_query
        
    entries = await TimeEntry.find(query).sort("-entry_date").to_list()
    
    rows = []
    for e in entries:
        emp = await Employee.find_one(Employee.id == e.employee_id)
        if not emp:
            continue
            
        rows.append({
            "date": str(e.entry_date),
            "last_name": emp.last_name,
            "first_name": emp.first_name,
            "department": emp.department or "",
            "entry_type": e.entry_type,
            "regular_hours": float(e.regular_hours or 0),
            "overtime_hours": float(e.overtime_hours or 0),
            "total_hours": float((e.regular_hours or 0) + (e.overtime_hours or 0)),
            "approved": e.approved,
            "notes": e.notes or "",
        })
    
    rows.sort(key=lambda x: x["date"], reverse=True)
    return csv_response(rows, "time-entries.csv")
