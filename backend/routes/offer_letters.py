import uuid
import os
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors
from models import Company
from utils.auth import get_current_user
from config import settings
from uuid import UUID

router = APIRouter(prefix="/offer-letters", tags=["offer-letters"])

# In-memory store for now, as the original code had it. 
# In a real app, this should be in MongoDB.
_offers: dict = {}


class OfferLetterRequest(BaseModel):
    candidate_name: str
    candidate_email: str
    job_title: str
    department: str
    pay_type: str = "salary"          # salary | hourly
    pay_rate: float = 0.0
    pay_frequency: str = "biweekly"
    start_date: date
    manager_name: str = ""
    office_location: str = ""
    offer_expiry_days: int = 7
    additional_notes: str = ""
    signing_name: str = ""
    signing_title: str = "Head of People Operations"


@router.post("", status_code=201)
async def generate_offer_letter(
    body: OfferLetterRequest,
    current_user: dict = Depends(get_current_user),
):
    company = await Company.find_one(Company.id == current_user["company_id"])
    company_name = company.name if company else "Company"
    company_addr = f"{company.address_line1 or ''}, {company.city or ''} {company.state or ''}" if company else ""

    offer_id = str(uuid.uuid4())
    os.makedirs(settings.PAYSTUB_DIR, exist_ok=True)
    pdf_path = os.path.join(settings.PAYSTUB_DIR, f"offer_{offer_id}.pdf")

    _build_offer_pdf(pdf_path, body, company_name, company_addr)
    _offers[offer_id] = {"path": pdf_path, "candidate": body.candidate_name, "created_at": datetime.utcnow().isoformat()}

    return {
        "offer_id": offer_id,
        "candidate_name": body.candidate_name,
        "download_url": f"/offer-letters/{offer_id}/download",
        "created_at": _offers[offer_id]["created_at"],
    }


@router.get("/{offer_id}/download")
async def download_offer_letter(
    offer_id: str,
    current_user: dict = Depends(get_current_user),
):
    offer = _offers.get(offer_id)
    if not offer or not os.path.exists(offer["path"]):
        raise HTTPException(404, "Offer letter not found")
    safe_name = offer["candidate"].replace(" ", "_")
    return FileResponse(offer["path"], media_type="application/pdf",
                        filename=f"offer_letter_{safe_name}.pdf")


def _build_offer_pdf(path: str, body: OfferLetterRequest, company_name: str, company_addr: str):
    doc = SimpleDocTemplate(path, pagesize=letter,
                            rightMargin=1*inch, leftMargin=1*inch,
                            topMargin=1*inch, bottomMargin=1*inch)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", fontSize=13, fontName="Helvetica-Bold", spaceAfter=4)
    body_style = ParagraphStyle("body", fontSize=10, fontName="Helvetica",
                                leading=16, spaceAfter=10)
    sig_style = ParagraphStyle("sig", fontSize=10, fontName="Helvetica", leading=16)
    center = ParagraphStyle("center", fontSize=10, fontName="Helvetica", alignment=TA_CENTER)
    small = ParagraphStyle("small", fontSize=9, fontName="Helvetica",
                           textColor=colors.HexColor("#666666"))

    pay_str = ""
    if body.pay_type == "salary":
        pay_str = f"${body.pay_rate:,.0f} per year"
    else:
        pay_str = f"${body.pay_rate:,.2f} per hour"

    expiry = f"{body.offer_expiry_days} days from the date of this letter"
    today = date.today().strftime("%B %d, %Y")

    story = [
        Paragraph(company_name, h1),
        Paragraph(company_addr, small),
        Spacer(1, 20),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a1a")),
        Spacer(1, 16),
        Paragraph(today, body_style),
        Spacer(1, 8),
        Paragraph(f"Dear {body.candidate_name},", body_style),
        Spacer(1, 8),
        Paragraph(
            f"We are delighted to offer you the position of <b>{body.job_title}</b> "
            f"in the <b>{body.department}</b> department at <b>{company_name}</b>. "
            f"We were impressed by your background and believe you will be a valuable "
            f"addition to our team.",
            body_style,
        ),
        Spacer(1, 8),
        Paragraph("<b>Position Details</b>", h1),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=8),
    ]

    details = [
        ("Job Title", body.job_title),
        ("Department", body.department),
        ("Start Date", body.start_date.strftime("%B %d, %Y")),
        ("Compensation", pay_str),
        ("Pay Schedule", body.pay_frequency.title()),
    ]
    if body.manager_name:
        details.append(("Reports To", body.manager_name))
    if body.office_location:
        details.append(("Work Location", body.office_location))

    for label, value in details:
        story.append(Paragraph(f"<b>{label}:</b> &nbsp;&nbsp; {value}", body_style))

    story += [
        Spacer(1, 8),
        Paragraph("<b>Benefits</b>", h1),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=8),
        Paragraph(
            "You will be eligible for our standard benefits package including health, "
            "dental, and vision insurance, 401(k) retirement plan with company match, "
            "paid time off, and other company benefits. Full details will be provided "
            "during your onboarding.",
            body_style,
        ),
        Spacer(1, 8),
    ]

    if body.additional_notes:
        story += [
            Paragraph("<b>Additional Terms</b>", h1),
            HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=8),
            Paragraph(body.additional_notes, body_style),
            Spacer(1, 8),
        ]

    story += [
        Paragraph(
            f"This offer is contingent upon successful completion of a background check "
            f"and reference verification. Please sign and return this offer letter within "
            f"{expiry} to confirm your acceptance.",
            body_style,
        ),
        Paragraph(
            "We are excited about the prospect of you joining our team and look forward "
            "to working together.",
            body_style,
        ),
        Spacer(1, 24),
        Paragraph("Sincerely,", sig_style),
        Spacer(1, 40),
        Paragraph(f"<b>{body.signing_name or company_name}</b>", sig_style),
        Paragraph(body.signing_title, small),
        Paragraph(company_name, small),
        Spacer(1, 32),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=8),
        Paragraph("<b>Candidate Acceptance</b>", h1),
        Spacer(1, 8),
        Paragraph("I accept the offer of employment on the terms described above.", body_style),
        Spacer(1, 32),
        Paragraph("Signature: _______________________________  Date: ____________", sig_style),
        Spacer(1, 16),
        Paragraph(f"Printed name: {body.candidate_name}", sig_style),
    ]

    doc.build(story)
