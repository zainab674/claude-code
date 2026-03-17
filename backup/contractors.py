"""
1099 contractor tracking.
Track payments to independent contractors for annual 1099-NEC filing.
Contractors paid $600+ in a year require a 1099-NEC.

POST /contractors            add contractor
GET  /contractors            list contractors
POST /contractors/{id}/payments  record payment
GET  /contractors/{id}/ytd   YTD payments summary
GET  /1099/report            1099-NEC report for all contractors
GET  /1099/xml               1099 data XML download
"""
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Numeric, Boolean, Date, DateTime, Integer, ForeignKey, Text, select, func
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(tags=["contractors"])

THRESHOLD_1099 = 600.00   # IRS 1099-NEC threshold


class Contractor(Base):
    __tablename__ = "contractors"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    business_name = Column(String(200))
    email = Column(String(255))
    phone = Column(String(20))
    ein_or_ssn_last4 = Column(String(4))       # last 4 only for display
    tin_encrypted = Column(String(500))         # Taxpayer ID encrypted
    address_line1 = Column(String(255))
    city = Column(String(100))
    state = Column(String(2))
    zip = Column(String(10))
    contractor_type = Column(String(30), default="individual")  # individual | business
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ContractorPayment(Base):
    __tablename__ = "contractor_payments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contractor_id = Column(UUID(as_uuid=True), ForeignKey("contractors.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    description = Column(Text)
    payment_method = Column(String(30), default="check")  # check|ach|wire|paypal|other
    reference_number = Column(String(100))
    tax_year = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(Contractor).where(Contractor.company_id == current_user["company_id"])
    if active_only:
        q = q.where(Contractor.is_active == True)
    q = q.order_by(Contractor.last_name, Contractor.first_name)
    result = await db.execute(q)
    return [_ser_contractor(c) for c in result.scalars().all()]


@router.post("/contractors", status_code=201)
async def create_contractor(
    body: ContractorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    contractor = Contractor(company_id=current_user["company_id"], **body.model_dump())
    db.add(contractor)
    await db.commit()
    await db.refresh(contractor)
    return _ser_contractor(contractor)


@router.get("/contractors/{contractor_id}")
async def get_contractor(
    contractor_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(Contractor).where(
            Contractor.id == contractor_id,
            Contractor.company_id == current_user["company_id"],
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contractor not found")
    return _ser_contractor(c)


@router.post("/contractors/{contractor_id}/payments", status_code=201)
async def record_payment(
    contractor_id: str,
    body: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Verify contractor belongs to company
    res = await db.execute(
        select(Contractor).where(
            Contractor.id == contractor_id,
            Contractor.company_id == current_user["company_id"],
        )
    )
    if not res.scalar_one_or_none():
        raise HTTPException(404, "Contractor not found")

    payment = ContractorPayment(
        contractor_id=contractor_id,
        company_id=current_user["company_id"],
        tax_year=body.payment_date.year,
        **body.model_dump(),
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return {
        "id": str(payment.id),
        "contractor_id": contractor_id,
        "payment_date": str(payment.payment_date),
        "amount": float(payment.amount),
        "description": payment.description,
        "payment_method": payment.payment_method,
        "tax_year": payment.tax_year,
    }


@router.get("/contractors/{contractor_id}/payments")
async def list_payments(
    contractor_id: str,
    year: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(ContractorPayment).where(
        ContractorPayment.contractor_id == contractor_id,
        ContractorPayment.company_id == current_user["company_id"],
    )
    if year:
        q = q.where(ContractorPayment.tax_year == year)
    q = q.order_by(ContractorPayment.payment_date.desc())
    result = await db.execute(q)
    payments = result.scalars().all()
    total = sum(float(p.amount) for p in payments)
    return {
        "contractor_id": contractor_id,
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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """1099-NEC report: all contractors paid $600+ in a year."""
    year = year or date.today().year
    result = await db.execute(
        select(
            Contractor.id, Contractor.first_name, Contractor.last_name,
            Contractor.business_name, Contractor.address_line1,
            Contractor.city, Contractor.state, Contractor.zip,
            Contractor.ein_or_ssn_last4, Contractor.contractor_type,
            func.sum(ContractorPayment.amount).label("total_paid"),
            func.count(ContractorPayment.id).label("payment_count"),
        )
        .join(ContractorPayment, Contractor.id == ContractorPayment.contractor_id)
        .where(
            Contractor.company_id == current_user["company_id"],
            ContractorPayment.tax_year == year,
        )
        .group_by(
            Contractor.id, Contractor.first_name, Contractor.last_name,
            Contractor.business_name, Contractor.address_line1,
            Contractor.city, Contractor.state, Contractor.zip,
            Contractor.ein_or_ssn_last4, Contractor.contractor_type,
        )
        .having(func.sum(ContractorPayment.amount) >= THRESHOLD_1099)
        .order_by(func.sum(ContractorPayment.amount).desc())
    )
    rows = result.all()

    contractors = [
        {
            "contractor_id": str(r.id),
            "name": r.business_name or f"{r.first_name} {r.last_name}",
            "first_name": r.first_name, "last_name": r.last_name,
            "contractor_type": r.contractor_type,
            "address": f"{r.address_line1 or ''} {r.city or ''} {r.state or ''} {r.zip or ''}".strip(),
            "tin_last4": r.ein_or_ssn_last4 or "****",
            "total_paid": round(float(r.total_paid), 2),
            "payment_count": r.payment_count,
            "requires_1099_nec": True,
        }
        for r in rows
    ]

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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await report_1099(year, db, current_user)
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
