"""
Paystub PDF Generator — complete, production-grade paystub.
Supports: weekly, biweekly, semimonthly, monthly
Includes:  all earnings types, ALL deductions (pretax + posttax + garnishments),
           YTD columns for every line, employer taxes (informational),
           W-2 reference boxes, pay frequency label, employee address.
"""
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from config import settings

_BLK  = colors.HexColor("#1a1a1a")
_GRY  = colors.HexColor("#f5f5f5")
_GRY2 = colors.HexColor("#f0f0f0")
_LT   = colors.HexColor("#e0e0e0")
_GRN  = colors.HexColor("#1a7a3c")
_RED  = colors.HexColor("#c0392b")
_MUT  = colors.HexColor("#666666")
_MUT2 = colors.HexColor("#999999")
_MUT3 = colors.HexColor("#bbbbbb")

def _f(v) -> str:
    return f"${float(v or 0):,.2f}"

def _p(text, size=9, bold=False, color=None, align=TA_LEFT) -> Paragraph:
    style = ParagraphStyle(
        "x", fontSize=size,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=color or _BLK,
        alignment=align,
    )
    return Paragraph(str(text), style)

FREQ_LABELS = {
    "weekly":      "Weekly (52/yr)",
    "biweekly":    "Bi-Weekly (26/yr)",
    "semimonthly": "Semi-Monthly (24/yr)",
    "monthly":     "Monthly (12/yr)",
}

def _table(data, widths, header_rows=1, total_rows=1):
    t = Table(data, colWidths=widths)
    base = [
        ("FONTSIZE", (0,0), (-1,-1), 8.5),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("GRID", (0,0), (-1,-1), 0.25, _LT),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
    ]
    for r in range(header_rows):
        base += [
            ("FONTNAME", (0,r), (-1,r), "Helvetica-Bold"),
            ("BACKGROUND", (0,r), (-1,r), _GRY2),
        ]
    for r in range(1, total_rows+1):
        base += [
            ("FONTNAME", (0,-r), (-1,-r), "Helvetica-Bold"),
            ("BACKGROUND", (0,-r), (-1,-r), _GRY),
        ]
    t.setStyle(TableStyle(base))
    return t

def _section(title) -> Paragraph:
    return Paragraph(
        title,
        ParagraphStyle("sh", fontSize=8, fontName="Helvetica-Bold",
                       backColor=_BLK, textColor=colors.white,
                       leftIndent=4, rightIndent=4,
                       spaceBefore=10, spaceAfter=0),
    )


def generate_paystub_pdf(
    employee: dict,
    company: dict,
    pay_period: dict,
    pay_item: dict,
    output_path: str = None,
) -> str:
    os.makedirs(settings.PAYSTUB_DIR, exist_ok=True)

    if not output_path:
        fn = f"paystub_{employee['id']}_{pay_period['period_end']}.pdf"
        output_path = os.path.join(settings.PAYSTUB_DIR, fn)

    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        rightMargin=0.5*inch, leftMargin=0.5*inch,
        topMargin=0.45*inch, bottomMargin=0.45*inch,
    )
    story = []
    W = 7.5 * inch  # usable width

    # ── Header: company left, PAY STUB right ─────────────────
    co_name   = company.get("name", "Company")
    co_addr   = f"{company.get('address_line1','')} · {company.get('city','')} {company.get('state','')} {company.get('zip','')}"
    co_ein    = f"EIN: {company.get('ein','N/A')}"
    freq      = FREQ_LABELS.get(employee.get("pay_frequency","biweekly"), "Bi-Weekly")

    hdr = Table([
        [_p(co_name, 16, True), _p("PAY STUB", 15, True, align=TA_RIGHT)],
        [_p(co_addr, 8, color=_MUT), _p(f"{co_ein}  ·  {freq}", 8, color=_MUT, align=TA_RIGHT)],
    ], colWidths=[4.5*inch, 3.0*inch])
    hdr.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story += [hdr, HRFlowable(width="100%", thickness=2, color=_BLK, spaceAfter=6)]

    # ── Employee / Period summary bar ────────────────────────
    emp_name   = f"{employee.get('first_name','')} {employee.get('last_name','')}"
    emp_dept   = employee.get("department","")
    emp_title  = employee.get("job_title","")
    emp_addr   = ", ".join(filter(None,[employee.get("address_line1",""),
                                        employee.get("city",""),
                                        employee.get("state",""),
                                        employee.get("zip","")]))
    emp_id     = str(employee.get("id",""))[:8]

    p_start = str(pay_period.get("period_start",""))
    p_end   = str(pay_period.get("period_end",""))
    p_pay   = str(pay_period.get("pay_date",""))
    net     = _f(pay_item.get("net_pay",0))

    bar = Table([
        [_p("EMPLOYEE",7,True,_MUT), _p("DEPARTMENT / TITLE",7,True,_MUT),
         _p("PAY PERIOD",7,True,_MUT), _p("PAY DATE",7,True,_MUT), _p("NET PAY",7,True,_MUT)],
        [_p(emp_name,9,True), _p(f"{emp_dept}\n{emp_title}",8),
         _p(f"{p_start} – {p_end}",9), _p(p_pay,9),
         _p(net,14,True,_GRN)],
        [_p(f"ID: {emp_id}",7,color=_MUT), _p("",7),
         _p("",7), _p("",7), _p("",7)],
    ], colWidths=[1.7*inch,1.6*inch,1.7*inch,1.1*inch,1.4*inch])
    bar.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),_GRY2),
        ("GRID",(0,0),(-1,-1),0.5,_LT),
        ("TOPPADDING",(0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ]))
    story += [bar, Spacer(1,8)]

    # ── Earnings ─────────────────────────────────────────────
    story.append(_section("EARNINGS"))
    earn = [["Description","Hours","Rate","Current","YTD"]]

    reg_hrs = pay_item.get("regular_hours",0) or 0
    ot_hrs  = pay_item.get("overtime_hours",0) or 0
    reg_pay = float(pay_item.get("regular_pay",0) or 0)
    ot_pay  = float(pay_item.get("overtime_pay",0) or 0)
    bon_pay = float(pay_item.get("bonus_pay",0) or 0)
    rei_pay = float(pay_item.get("reimbursement",0) or 0)
    gross   = float(pay_item.get("gross_pay",0) or 0)
    ytd_gr  = float(pay_item.get("ytd_gross",0) or 0)

    # Determine hourly rate display
    pay_rate = float(employee.get("pay_rate",0) or 0)
    is_hourly = employee.get("pay_type","salary") == "hourly"
    rate_disp = _f(pay_rate) if is_hourly else "—"

    if reg_pay:
        earn.append(["Regular Pay", str(int(reg_hrs)) if reg_hrs else "—", rate_disp, _f(reg_pay), ""])
    if ot_pay:
        ot_rate = pay_rate * 1.5 if is_hourly else 0
        earn.append(["Overtime (1.5×)", str(int(ot_hrs)) if ot_hrs else "—",
                     _f(ot_rate) if ot_rate else "—", _f(ot_pay), ""])
    if bon_pay:
        earn.append(["Bonus Pay", "—", "—", _f(bon_pay), ""])
    if rei_pay:
        earn.append(["Reimbursement (non-taxable)", "—", "—", _f(rei_pay), ""])
    earn.append(["GROSS PAY", "", "", _f(gross), _f(ytd_gr)])

    story.append(_table(earn, [2.8*inch,0.7*inch,0.8*inch,1.1*inch,1.1*inch]))

    # ── Pre-tax deductions ────────────────────────────────────
    pretax_rows = [
        ("Health Insurance",  "health_insurance",  ""),
        ("Dental Insurance",  "dental_insurance",  ""),
        ("Vision Insurance",  "vision_insurance",  ""),
        ("401(k) Retirement", "retirement_401k",   "ytd_401k"),
        ("HSA",               "hsa",               ""),
        ("FSA",               "fsa",               ""),
    ]
    pre_data = [["Pre-Tax Deduction","Current","YTD"]]
    for lbl, key, ytd_key in pretax_rows:
        v = float(pay_item.get(key,0) or 0)
        if v:
            ytd_v = float(pay_item.get(ytd_key,0) or 0) if ytd_key else 0
            pre_data.append([lbl, _f(v), _f(ytd_v) if ytd_v else ""])
    total_pre = float(pay_item.get("total_pretax_deductions",0) or 0)
    pre_data.append(["TOTAL PRE-TAX", _f(total_pre), ""])

    if len(pre_data) > 2:
        story += [_section("PRE-TAX DEDUCTIONS"),
                  _table(pre_data,[3.6*inch,1.4*inch,1.4*inch])]

    # ── Taxes withheld ────────────────────────────────────────
    story.append(_section("TAXES WITHHELD"))
    tax_rows = [
        ("Federal Income Tax",          "federal_income_tax",       "ytd_federal"),
        ("State Income Tax",            "state_income_tax",         "ytd_state"),
        ("Social Security (6.2%)",      "social_security_tax",      "ytd_ss"),
        ("Medicare (1.45%)",            "medicare_tax",             "ytd_medicare"),
        ("Additional Medicare (0.9%)",  "additional_medicare_tax",  ""),
    ]
    tax_data = [["Tax","Current","YTD"]]
    for lbl, key, ytd_key in tax_rows:
        v = float(pay_item.get(key,0) or 0)
        if v:
            ytd_v = float(pay_item.get(ytd_key,0) or 0) if ytd_key else 0
            tax_data.append([lbl, _f(v), _f(ytd_v) if ytd_v else ""])
    total_tax = float(pay_item.get("total_employee_taxes",0) or 0)
    ytd_tax   = sum(float(pay_item.get(r[2],0) or 0) for r in tax_rows if r[2])
    tax_data.append(["TOTAL TAXES WITHHELD", _f(total_tax), _f(ytd_tax) if ytd_tax else ""])
    story.append(_table(tax_data,[3.6*inch,1.4*inch,1.4*inch]))

    # ── Post-tax deductions (garnishments etc.) ───────────────
    post_rows = [
        ("Wage Garnishment",       "garnishment",           ""),
        ("Child Support",          "child_support",         ""),
        ("Other Post-tax",         "other_post_tax",        ""),
    ]
    post_data = [["Post-Tax Deduction","Current","YTD"]]
    for lbl, key, ytd_key in post_rows:
        v = float(pay_item.get(key,0) or 0)
        if v:
            post_data.append([lbl, _f(v), ""])
    total_post = float(pay_item.get("total_posttax_deductions",0) or 0)
    if total_post:
        post_data.append(["TOTAL POST-TAX", _f(total_post), ""])

    if len(post_data) > 2:
        story += [_section("POST-TAX DEDUCTIONS / GARNISHMENTS"),
                  _table(post_data,[3.6*inch,1.4*inch,1.4*inch])]

    # ── Employer taxes (informational) ───────────────────────
    er_rows = [
        ("Employer Social Security (6.2%)", "employer_social_security"),
        ("Employer Medicare (1.45%)",        "employer_medicare"),
        ("FUTA (federal unemployment)",      "futa_tax"),
        ("SUTA (state unemployment)",        "suta_tax"),
    ]
    er_data = [["Employer Tax (informational — not deducted from you)","Current"]]
    for lbl, key in er_rows:
        v = float(pay_item.get(key,0) or 0)
        if v:
            er_data.append([lbl, _f(v)])
    total_er = float(pay_item.get("total_employer_taxes",0) or 0)
    if total_er:
        er_data.append(["TOTAL EMPLOYER TAXES", _f(total_er)])

    if len(er_data) > 2:
        story += [_section("EMPLOYER TAXES (paid by employer — shown for your records)"),
                  _table(er_data,[6.0*inch,1.5*inch])]

    # ── Net pay summary ───────────────────────────────────────
    story.append(Spacer(1,10))
    ytd_net = float(pay_item.get("ytd_net",0) or 0)
    summary = [
        ["Gross Pay",                    _f(gross),      _f(ytd_gr)],
        ["Less: Pre-tax Deductions",     f"({_f(float(pay_item.get('total_pretax_deductions',0) or 0))})", ""],
        ["Less: Taxes Withheld",         f"({_f(total_tax)})", ""],
        ["Less: Post-tax Deductions",    f"({_f(float(pay_item.get('total_posttax_deductions',0) or 0))})", ""],
        ["NET PAY",                      _f(float(pay_item.get('net_pay',0) or 0)), _f(ytd_net)],
    ]
    st = Table(
        [[_p(r[0],9 if i<4 else 12, i==4, _GRN if i==4 else None),
          _p(r[1],9 if i<4 else 12, i==4, _GRN if i==4 else None, TA_RIGHT),
          _p(r[2],9,False,_MUT,TA_RIGHT)] for i,r in enumerate(summary)],
        colWidths=[4.5*inch,1.5*inch,1.5*inch]
    )
    st.setStyle(TableStyle([
        ("LINEABOVE",(0,-1),(-1,-1),1.5,_BLK),
        ("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ("BACKGROUND",(0,-1),(-1,-1),_GRY),
    ]))
    story.append(st)

    # ── W-2 Reference boxes ───────────────────────────────────
    story.append(Spacer(1,10))
    story.append(_section("W-2 REFERENCE (estimated year-to-date)"))
    ytd_fed    = float(pay_item.get("ytd_federal",0) or 0)
    ytd_ss     = float(pay_item.get("ytd_ss",0) or 0)
    ytd_med    = float(pay_item.get("ytd_medicare",0) or 0)
    ytd_401k   = float(pay_item.get("ytd_401k",0) or 0)
    ytd_state  = float(pay_item.get("ytd_state",0) or 0)
    ytd_ss_wg  = float(pay_item.get("ytd_ss_wages",0) or ytd_gr)

    w2 = [
        ["Box","Description","YTD Amount"],
        ["1",  "Wages, tips (taxable gross)", _f(ytd_gr - float(pay_item.get("ytd_pretax_deductions",0) or 0))],
        ["2",  "Federal income tax withheld", _f(ytd_fed)],
        ["3",  "Social security wages",       _f(min(ytd_ss_wg,168600))],
        ["4",  "Social security tax withheld",_f(ytd_ss)],
        ["5",  "Medicare wages",              _f(ytd_gr)],
        ["6",  "Medicare tax withheld",       _f(ytd_med)],
        ["12D","401(k) contributions",        _f(ytd_401k)],
        ["16", "State wages",                 _f(ytd_gr)],
        ["17", "State income tax",            _f(ytd_state)],
    ]
    story.append(_table(w2,[0.5*inch,3.8*inch,2.2*inch]))

    # ── Footer ────────────────────────────────────────────────
    story.append(Spacer(1,12))
    story.append(HRFlowable(width="100%",thickness=0.5,color=_LT,spaceAfter=4))
    for txt, sz, col in [
        ("This is an official payroll document generated by PayrollOS. "
         "Keep this for your tax records.", 7, _MUT2),
        (f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC", 7, _MUT3),
    ]:
        story.append(Paragraph(txt, ParagraphStyle("ft",fontSize=sz,
                               textColor=col,alignment=TA_CENTER)))

    doc.build(story)
    return output_path
