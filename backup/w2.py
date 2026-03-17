"""
W-2 XML generator — produces IRS-compatible W-2 data for annual filing.
Generates both:
  1. Per-employee W-2 summary JSON (for display/review)
  2. EFW2 format (SSA electronic filing format) for bulk submission

GET /w2/{year}           → W-2 data for all employees
GET /w2/{year}/xml       → EFW2 XML download
GET /w2/{year}/{emp_id}  → Single employee W-2

NOTE: This is a W-2 DATA generator, not a certified filer.
For actual IRS/SSA submission, use a licensed payroll provider.
"""
import xml.etree.ElementTree as ET
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import Employee, PayRunItem, PayRun, PayPeriod, Company
from utils.auth import get_current_user

router = APIRouter(prefix="/w2", tags=["w2"])


@router.get("/{year}")
async def get_w2_data(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return W-2 data for all employees for a given tax year."""
    rows = await _fetch_ytd(db, current_user["company_id"], year)
    co = await _fetch_company(db, current_user["company_id"])

    w2s = []
    for r in rows:
        # Box 12: 401(k) contributions (code D)
        box12_d = round(float(r.ytd_401k or 0), 2)
        # Taxable wages (Box 1) = gross - pretax deductions
        box1 = round(float(r.ytd_gross or 0) - float(r.ytd_pretax or 0), 2)
        # Box 3: SS wages (capped at $168,600)
        box3 = round(min(float(r.ytd_gross or 0), 168600.0), 2)
        # Box 5: Medicare wages (no cap)
        box5 = round(float(r.ytd_gross or 0), 2)

        w2s.append({
            "employee_id": str(r.id),
            "name": f"{r.last_name}, {r.first_name}",
            "first_name": r.first_name,
            "last_name": r.last_name,
            "state": r.state_code or "NY",
            "filing_status": r.filing_status or "single",
            "tax_year": year,
            # W-2 Boxes
            "box1_wages_tips":          box1,
            "box2_federal_withheld":    round(float(r.ytd_federal or 0), 2),
            "box3_ss_wages":            box3,
            "box4_ss_withheld":         round(float(r.ytd_ss or 0), 2),
            "box5_medicare_wages":      box5,
            "box6_medicare_withheld":   round(float(r.ytd_medicare or 0), 2),
            "box12_code_d_401k":        box12_d,
            "box16_state_wages":        box1,
            "box17_state_income_tax":   round(float(r.ytd_state or 0), 2),
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Download EFW2-style XML for all employees."""
    data = await get_w2_data(year, db, current_user)
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await get_w2_data(year, db, current_user)
    match = next((w for w in data["w2s"] if w["employee_id"] == employee_id), None)
    if not match:
        from fastapi import HTTPException
        raise HTTPException(404, "W-2 not found for this employee/year")
    return match


# ── Helpers ────────────────────────────────────────────────────
async def _fetch_ytd(db, company_id, year):
    return (await db.execute(
        select(
            Employee.id, Employee.first_name, Employee.last_name,
            Employee.state_code, Employee.filing_status,
            func.sum(PayRunItem.gross_pay).label("ytd_gross"),
            func.sum(PayRunItem.federal_income_tax).label("ytd_federal"),
            func.sum(PayRunItem.state_income_tax).label("ytd_state"),
            func.sum(PayRunItem.social_security_tax).label("ytd_ss"),
            func.sum(PayRunItem.medicare_tax).label("ytd_medicare"),
            func.sum(PayRunItem.retirement_401k).label("ytd_401k"),
            func.sum(PayRunItem.total_pretax_deductions).label("ytd_pretax"),
        )
        .join(PayRunItem, Employee.id == PayRunItem.employee_id)
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            Employee.company_id == company_id,
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
        .group_by(Employee.id, Employee.first_name, Employee.last_name,
                  Employee.state_code, Employee.filing_status)
    )).all()


async def _fetch_company(db, company_id):
    return (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()


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
