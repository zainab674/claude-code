import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Response, HTTPException
from models import Employee, PayRunItem, PayRun, PayPeriod, Company
from utils.auth import get_current_user
from uuid import UUID
from utils.numbers import to_float

router = APIRouter(prefix="/w2", tags=["w2"])


@router.get("/{year}")
async def get_w2_data(
    year: int,
    current_user: dict = Depends(get_current_user),
):
    """Return W-2 data for all employees for a given tax year."""
    company_id = current_user["company_id"]
    rows = await _fetch_ytd(company_id, year)
    co = await Company.find_one(Company.id == company_id)

    w2s = []
    for r in rows:
        # Box 12: 401(k) contributions (code D)
        box12_d = round(to_float(r["ytd_401k"]), 2)
        # Taxable wages (Box 1) = gross - pretax deductions
        box1 = round(to_float(r["ytd_gross"]) - to_float(r["ytd_pretax"]), 2)
        # Box 3: SS wages (capped at $168,600 for 2024 - should be dynamic but keeping logic)
        box3 = round(min(to_float(r["ytd_gross"]), 168600.0), 2)
        # Box 5: Medicare wages (no cap)
        box5 = round(to_float(r["ytd_gross"]), 2)

        emp = await Employee.find_one(Employee.id == r["_id"])
        if not emp:
            continue

        w2s.append({
            "employee_id": str(emp.id),
            "name": f"{emp.last_name}, {emp.first_name}",
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "state": emp.state_code or "NY",
            "filing_status": emp.filing_status or "single",
            "tax_year": year,
            # W-2 Boxes
            "box1_wages_tips":          box1,
            "box2_federal_withheld":    round(to_float(r["ytd_federal"]), 2),
            "box3_ss_wages":            box3,
            "box4_ss_withheld":         round(to_float(r["ytd_ss"]), 2),
            "box5_medicare_wages":      box5,
            "box6_medicare_withheld":   round(to_float(r["ytd_medicare"]), 2),
            "box12_code_d_401k":        box12_d,
            "box16_state_wages":        box1,
            "box17_state_income_tax":   round(to_float(r["ytd_state"]), 2),
            "employer": {
                "name": co.name if co else "",
                "ein": co.ein if co else "",
                "address": f"{co.address_line1 or ''} {co.city or ''} {co.state or ''} {co.zip or ''}".strip() if co else "",
            },
        })

    return {
        "year": year,
        "company": co.name if co else "",
        "employee_count": len(w2s),
        "w2s": w2s,
        "disclaimer": "W-2 data only. Do not submit to IRS/SSA without a licensed payroll provider.",
    }


@router.get("/{year}/xml")
async def download_w2_xml(
    year: int,
    current_user: dict = Depends(get_current_user),
):
    """Download EFW2-style XML for all employees."""
    data = await get_w2_data(year, current_user)
    xml_content = _build_efw2_xml(data["w2s"], year)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="w2-{year}.xml"'},
    )


@router.get("/{year}/{employee_id}")
async def get_single_w2(
    year: int,
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    data = await get_w2_data(year, current_user)
    match = next((w for w in data["w2s"] if w["employee_id"] == employee_id), None)
    if not match:
        raise HTTPException(404, "W-2 not found for this employee/year")
    return match


# ── Helpers ────────────────────────────────────────────────────
async def _fetch_ytd(company_id: UUID, year: int):
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)
    
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
        {"$match": {"period.period_start": {"$gte": year_start, "$lte": year_end}}},
        {
            "$group": {
                "_id": "$employee_id",
                "ytd_gross": {"$sum": "$gross_pay"},
                "ytd_federal": {"$sum": "$federal_income_tax"},
                "ytd_state": {"$sum": "$state_income_tax"},
                "ytd_ss": {"$sum": "$social_security_tax"},
                "ytd_medicare": {"$sum": "$medicare_tax"},
                "ytd_401k": {"$sum": "$retirement_401k"},
                "ytd_pretax": {"$sum": "$total_pretax_deductions"},
            }
        }
    ]
    
    return await PayRunItem.aggregate(pipeline).to_list()


def _build_efw2_xml(w2s: list, year: int) -> str:
    """Build simplified EFW2-compatible XML."""
    root = ET.Element("W2Transmittal")
    root.set("xmlns", "urn:payrollos:w2")
    root.set("taxYear", str(year))
    root.set("generated", date.today().isoformat())

    for w in w2s:
        emp_el = ET.SubElement(root, "W2")
        def add(tag, val):
            el = ET.SubElement(emp_el, tag)
            el.text = str(val) if val is not None else ""

        add("EmployeeID",         w["employee_id"])
        add("LastName",           w["last_name"])
        add("FirstName",          w["first_name"])
        add("State",              w["state"])
        add("FilingStatus",       w["filing_status"])
        add("Box1WagesTips",      f"{w['box1_wages_tips']:.2f}")
        add("Box2FederalTax",     f"{w['box2_federal_withheld']:.2f}")
        add("Box3SSWages",        f"{w['box3_ss_wages']:.2f}")
        add("Box4SSTax",          f"{w['box4_ss_withheld']:.2f}")
        add("Box5MedicareWages",  f"{w['box5_medicare_wages']:.2f}")
        add("Box6MedicareTax",    f"{w['box6_medicare_withheld']:.2f}")
        add("Box12D401k",         f"{w['box12_code_d_401k']:.2f}")
        add("Box16StateWages",    f"{w['box16_state_wages']:.2f}")
        add("Box17StateTax",      f"{w['box17_state_income_tax']:.2f}")

        er = ET.SubElement(emp_el, "Employer")
        ET.SubElement(er, "Name").text = w["employer"]["name"]
        ET.SubElement(er, "EIN").text = w["employer"]["ein"]
        ET.SubElement(er, "Address").text = w["employer"]["address"]

    return ET.tostring(root, encoding="unicode", xml_declaration=False)
