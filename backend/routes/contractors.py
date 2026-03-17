"""
1099 contractor tracking.
Migrated to Beanie (MongoDB).
"""
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from models import Contractor, ContractorPayment
from utils.auth import get_current_user
from utils.numbers import to_float

router = APIRouter(tags=["contractors"])

THRESHOLD_1099 = 600.00   # IRS 1099-NEC threshold


class ContractorCreate(BaseModel):
    first_name: str
    last_name: str
    business_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    ein_or_ssn_last4: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    contractor_type: str = "individual"


class PaymentCreate(BaseModel):
    payment_date: date
    amount: float
    description: Optional[str] = None
    payment_method: str = "check"
    reference_number: Optional[str] = None


@router.get("/contractors")
async def list_contractors(
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if active_only:
        query["is_active"] = True
    
    contractors = await Contractor.find(query).sort("last_name", "first_name").to_list()
    return [_ser_contractor(c) for c in contractors]


@router.post("/contractors", status_code=201)
async def create_contractor(
    body: ContractorCreate,
    current_user: dict = Depends(get_current_user),
):
    contractor = Contractor(
        company_id=current_user["company_id"], 
        **body.model_dump()
    )
    await contractor.insert()
    return _ser_contractor(contractor)


@router.get("/contractors/{contractor_id}")
async def get_contractor(
    contractor_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
):
    c = await Contractor.find_one(
        Contractor.id == contractor_id,
        Contractor.company_id == current_user["company_id"]
    )
    if not c:
        raise HTTPException(404, "Contractor not found")
    return _ser_contractor(c)


@router.post("/contractors/{contractor_id}/payments", status_code=201)
async def record_payment(
    contractor_id: uuid.UUID,
    body: PaymentCreate,
    current_user: dict = Depends(get_current_user),
):
    # Verify contractor belongs to company
    comp_id = current_user["company_id"]
    c = await Contractor.find_one(Contractor.id == contractor_id, Contractor.company_id == comp_id)
    if not c:
        raise HTTPException(404, "Contractor not found")

    payment = ContractorPayment(
        contractor_id=contractor_id,
        company_id=comp_id,
        tax_year=body.payment_date.year,
        **body.model_dump()
    )
    await payment.insert()
    
    return {
        "id": str(payment.id),
        "contractor_id": str(contractor_id),
        "payment_date": str(payment.payment_date),
        "amount": float(payment.amount),
        "description": payment.description,
        "payment_method": payment.payment_method,
        "tax_year": payment.tax_year,
    }


@router.get("/contractors/{contractor_id}/payments")
async def list_payments(
    contractor_id: uuid.UUID,
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    comp_id = current_user["company_id"]
    query = {
        "contractor_id": contractor_id,
        "company_id": comp_id
    }
    if year:
        query["tax_year"] = year
        
    payments = await ContractorPayment.find(query).sort("-payment_date").to_list()
    total = sum(float(p.amount) for p in payments)
    
    return {
        "contractor_id": str(contractor_id),
        "year": year,
        "total_paid": round(total, 2),
        "requires_1099": total >= THRESHOLD_1099,
        "payments": [
            {
                "id": str(p.id),
                "date": str(p.payment_date),
                "amount": float(p.amount),
                "description": p.description,
                "method": p.payment_method,
            }
            for p in payments
        ],
    }


@router.get("/1099/report")
async def report_1099(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    """1099-NEC report: all contractors paid $600+ in a year."""
    year = year or date.today().year
    comp_id = current_user["company_id"]
    
    # Use aggregation to find contractors with total payments >= threshold
    pipeline = [
        {"$match": {"company_id": comp_id, "tax_year": year}},
        {"$group": {
            "_id": "$contractor_id",
            "total_paid": {"$sum": "$amount"},
            "payment_count": {"$sum": 1}
        }},
        {"$match": {"total_paid": {"$gte": THRESHOLD_1099}}}
    ]
    
    results = await ContractorPayment.aggregate(pipeline).to_list()
    
    contractors = []
    for r in results:
        cid = r["_id"]
        c = await Contractor.get(cid)
        if c:
            contractors.append({
                "contractor_id": str(c.id),
                "name": c.business_name or f"{c.first_name} {c.last_name}",
                "first_name": c.first_name, "last_name": c.last_name,
                "contractor_type": c.contractor_type,
                "address": f"{c.address_line1 or ''} {c.city or ''} {c.state or ''} {c.zip or ''}".strip(),
                "tin_last4": c.ein_or_ssn_last4 or "****",
                "total_paid": round(to_float(r["total_paid"]), 2),
                "payment_count": r["payment_count"],
                "requires_1099_nec": True,
            })
            
    # Sort by total_paid desc
    contractors.sort(key=lambda x: x["total_paid"], reverse=True)

    return {
        "year": year,
        "threshold": THRESHOLD_1099,
        "total_contractors_requiring_1099": len(contractors),
        "total_payments": round(sum(c["total_paid"] for c in contractors), 2),
        "contractors": contractors,
        "disclaimer": "1099-NEC data only. File via IRS FIRE system or licensed tax preparer.",
    }


@router.get("/1099/xml")
async def download_1099_xml(
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    data = await report_1099(year, current_user)
    year_val = data["year"]
    root = ET.Element("Form1099NECTransmittal")
    root.set("taxYear", str(year_val))
    root.set("generated", date.today().isoformat())

    for c in data["contractors"]:
        el = ET.SubElement(root, "Form1099NEC")
        ET.SubElement(el, "ContractorID").text = c["contractor_id"]
        ET.SubElement(el, "Name").text = c["name"]
        ET.SubElement(el, "TINLast4").text = c["tin_last4"]
        ET.SubElement(el, "Address").text = c["address"]
        ET.SubElement(el, "Box1NonemployeeCompensation").text = f"{c['total_paid']:.2f}"
        ET.SubElement(el, "Box4FederalTaxWithheld").text = "0.00"

    xml_content = ET.tostring(root, encoding="unicode", xml_declaration=False)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="1099-nec-{year_val}.xml"'},
    )


def _ser_contractor(c: Contractor) -> dict:
    return {
        "id": str(c.id),
        "name": c.business_name or f"{c.first_name} {c.last_name}",
        "first_name": c.first_name, "last_name": c.last_name,
        "business_name": c.business_name,
        "email": c.email, "phone": c.phone,
        "contractor_type": c.contractor_type,
        "tin_last4": c.ein_or_ssn_last4,
        "address_line1": c.address_line1, "city": c.city,
        "state": c.state, "zip": c.zip,
        "is_active": c.is_active,
        "created_at": str(c.created_at),
    }
