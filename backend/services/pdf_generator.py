"""
Paystub PDF Generator
Generates professional paystub PDFs using ReportLab (free, no API needed)
"""
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from config import settings


def fmt(amount) -> str:
    v = float(amount) if amount else 0.0
    return f"${v:,.2f}"


def generate_paystub_pdf(
    employee: dict,
    company: dict,
    pay_period: dict,
    pay_item: dict,
    output_path: str = None,
) -> str:
    """
    Generate a paystub PDF and return the file path.

    All dicts have the same keys as the model fields.
    """
    os.makedirs(settings.PAYSTUB_DIR, exist_ok=True)

    if not output_path:
        filename = f"paystub_{employee['id']}_{pay_period['period_end']}.pdf"
        output_path = os.path.join(settings.PAYSTUB_DIR, filename)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Header ────────────────────────────────────────────────
    header_style = ParagraphStyle("header", fontSize=18, fontName="Helvetica-Bold", spaceAfter=4)
    sub_style = ParagraphStyle("sub", fontSize=10, fontName="Helvetica", textColor=colors.HexColor("#666666"))
    label_style = ParagraphStyle("label", fontSize=8, fontName="Helvetica-Bold", textColor=colors.HexColor("#444444"))
    value_style = ParagraphStyle("value", fontSize=10, fontName="Helvetica")

    header_data = [
        [
            Paragraph(company.get("name", "Company Name"), header_style),
            Paragraph("PAY STUB", ParagraphStyle("ps", fontSize=14, fontName="Helvetica-Bold", alignment=TA_RIGHT))
        ],
        [
            Paragraph(f"{company.get('address_line1','')} · {company.get('city','')} {company.get('state','')} {company.get('zip','')}", sub_style),
            Paragraph(f"EIN: {company.get('ein','N/A')}", ParagraphStyle("ein", fontSize=9, alignment=TA_RIGHT, textColor=colors.HexColor("#666666")))
        ],
    ]
    t = Table(header_data, colWidths=[4.5 * inch, 2.5 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a1a"), spaceAfter=8))

    # ── Employee & Period Info ─────────────────────────────────
    emp_name = f"{employee.get('first_name','')} {employee.get('last_name','')}"
    period_start = str(pay_period.get("period_start", ""))
    period_end = str(pay_period.get("period_end", ""))
    pay_date = str(pay_period.get("pay_date", ""))

    info_data = [
        [
            Paragraph("EMPLOYEE", label_style),
            Paragraph("PAY PERIOD", label_style),
            Paragraph("PAY DATE", label_style),
            Paragraph("NET PAY", label_style),
        ],
        [
            Paragraph(emp_name, value_style),
            Paragraph(f"{period_start} – {period_end}", value_style),
            Paragraph(pay_date, value_style),
            Paragraph(fmt(pay_item.get("net_pay", 0)),
                      ParagraphStyle("netpay", fontSize=14, fontName="Helvetica-Bold",
                                     textColor=colors.HexColor("#1a7a3c"))),
        ],
        [
            Paragraph(employee.get("job_title", ""), sub_style),
            Paragraph("", sub_style),
            Paragraph("", sub_style),
            Paragraph("", sub_style),
        ],
    ]
    t2 = Table(info_data, colWidths=[2.0 * inch, 2.0 * inch, 1.5 * inch, 1.5 * inch])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t2)
    story.append(Spacer(1, 12))

    # ── Earnings Table ────────────────────────────────────────
    def section_header(title):
        return Paragraph(title, ParagraphStyle("sh", fontSize=9, fontName="Helvetica-Bold",
                                               backColor=colors.HexColor("#1a1a1a"),
                                               textColor=colors.white,
                                               leftIndent=4, spaceBefore=8))

    story.append(section_header("EARNINGS"))
    earnings_data = [["Description", "Hours", "Rate", "Current", "YTD"]]

    if pay_item.get("regular_pay", 0):
        hrs = pay_item.get("regular_hours", 0) or "—"
        earnings_data.append(["Regular Pay", str(hrs), "", fmt(pay_item["regular_pay"]), ""])
    if pay_item.get("overtime_pay", 0):
        earnings_data.append(["Overtime (1.5×)", str(pay_item.get("overtime_hours", 0)), "", fmt(pay_item["overtime_pay"]), ""])
    if pay_item.get("bonus_pay", 0):
        earnings_data.append(["Bonus", "—", "", fmt(pay_item["bonus_pay"]), ""])
    if pay_item.get("commission_pay", 0):
        earnings_data.append(["Commission", "—", "", fmt(pay_item["commission_pay"]), ""])
    if pay_item.get("reimbursement", 0):
        earnings_data.append(["Reimbursement (non-taxable)", "—", "", fmt(pay_item["reimbursement"]), ""])

    earnings_data.append(["GROSS PAY", "", "", fmt(pay_item.get("gross_pay", 0)),
                          fmt(pay_item.get("ytd_gross", 0))])

    et = Table(earnings_data, colWidths=[2.8 * inch, 0.8 * inch, 0.8 * inch, 1.2 * inch, 1.4 * inch])
    et.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(et)

    # ── Deductions ────────────────────────────────────────────
    story.append(section_header("PRE-TAX DEDUCTIONS"))
    deduct_data = [["Description", "Current", "YTD"]]

    pretax_items = [
        ("Health Insurance", "health_insurance"),
        ("Dental Insurance", "dental_insurance"),
        ("Vision Insurance", "vision_insurance"),
        ("401(k) Retirement", "retirement_401k"),
        ("HSA", "hsa"),
    ]
    for label, key in pretax_items:
        val = pay_item.get(key, 0)
        if val:
            deduct_data.append([label, fmt(val), ""])
    deduct_data.append(["TOTAL PRE-TAX", fmt(pay_item.get("total_pretax_deductions", 0)), ""])

    dt = Table(deduct_data, colWidths=[3.6 * inch, 1.4 * inch, 1.4 * inch] if len(deduct_data[0]) == 3 else [3.6*inch, 1.4*inch, 1.4*inch])
    dt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(dt)

    # ── Taxes ─────────────────────────────────────────────────
    story.append(section_header("TAXES WITHHELD"))
    tax_data = [["Description", "Current", "YTD"]]
    tax_items = [
        ("Federal Income Tax", "federal_income_tax", "ytd_federal_tax"),
        ("State Income Tax", "state_income_tax", ""),
        ("Social Security (6.2%)", "social_security_tax", "ytd_social_security"),
        ("Medicare (1.45%)", "medicare_tax", "ytd_medicare"),
        ("Additional Medicare (0.9%)", "additional_medicare_tax", ""),
        ("Local Tax", "local_income_tax", ""),
    ]
    for label, key, ytd_key in tax_items:
        val = pay_item.get(key, 0)
        if val:
            ytd = pay_item.get(ytd_key, 0) if ytd_key else 0
            tax_data.append([label, fmt(val), fmt(ytd) if ytd else ""])
    tax_data.append(["TOTAL TAXES", fmt(pay_item.get("total_employee_taxes", 0)),
                     fmt(pay_item.get("ytd_federal_tax", 0))])

    tt = Table(tax_data, colWidths=[3.6 * inch, 1.4 * inch, 1.4 * inch])
    tt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(tt)

    # ── Employer Taxes (informational) ────────────────────────
    story.append(section_header("EMPLOYER TAXES (Your employer pays)"))
    emp_tax_data = [["Description", "Current"]]
    emp_tax_items = [
        ("Employer Social Security (6.2%)", "employer_social_security"),
        ("Employer Medicare (1.45%)", "employer_medicare"),
        ("FUTA (0.6%)", "futa_tax"),
    ]
    for label, key in emp_tax_items:
        val = pay_item.get(key, 0)
        if val:
            emp_tax_data.append([label, fmt(val)])
    emp_tax_data.append(["TOTAL EMPLOYER TAXES", fmt(pay_item.get("total_employer_taxes", 0))])

    emt = Table(emp_tax_data, colWidths=[5.0 * inch, 1.4 * inch])
    emt.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f5f5f5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(emt)

    # ── Net Pay Summary ───────────────────────────────────────
    story.append(Spacer(1, 12))
    summary_data = [
        ["Gross Pay", fmt(pay_item.get("gross_pay", 0))],
        ["Less: Pre-tax Deductions", f"({fmt(pay_item.get('total_pretax_deductions', 0))})"],
        ["Less: Taxes", f"({fmt(pay_item.get('total_employee_taxes', 0))})"],
        ["Less: Post-tax Deductions", f"({fmt(pay_item.get('total_posttax_deductions', 0))})"],
        ["NET PAY", fmt(pay_item.get("net_pay", 0))],
    ]
    st = Table(summary_data, colWidths=[5.0 * inch, 1.5 * inch])
    st.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 13),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#1a7a3c")),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#1a1a1a")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(st)

    # ── Footer ────────────────────────────────────────────────
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=6))
    story.append(Paragraph(
        "This is an official payroll document. Generated by PayrollOS. "
        "Tax calculations are estimates — consult a licensed payroll provider for compliance.",
        ParagraphStyle("footer", fontSize=7, textColor=colors.HexColor("#999999"), alignment=TA_CENTER)
    ))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ParagraphStyle("ts", fontSize=7, textColor=colors.HexColor("#bbbbbb"), alignment=TA_CENTER)
    ))

    doc.build(story)
    return output_path
