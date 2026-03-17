"""
Portal filing guide routes.
These produce step-by-step instructions + pre-filled data packages for
the three external portals that cannot be fully automated:

  1. SSA Business Services Online (W-2 filing)
  2. IRS IRIS (1099-NEC e-filing)
  3. State ACH tax payment portals

GET  /filing/ssa-w2/{year}        → instructions + W-2 data package ready to upload
GET  /filing/irs-iris/{year}      → instructions + 1099 data package + XML
GET  /filing/state-ach/{year}     → state-by-state instructions + payment amounts
GET  /filing/deadlines/{year}     → all filing deadlines for the year
POST /filing/ssa-w2/package/{year}  → download W-2 submission package (EFW2 format)
POST /filing/irs-iris/package/{year} → download 1099 IRIS submission package
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database import get_db
from models import Employee, PayRunItem, PayRun, PayPeriod, Company
from utils.auth import get_current_user

router = APIRouter(prefix="/filing", tags=["filing"])


# ── SSA Business Services Online — W-2 ────────────────────────
@router.get("/ssa-w2/{year}")
async def ssa_w2_guide(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Step-by-step guide + pre-filled data for W-2 submission to SSA BSO.
    """
    # Get W-2 data
    co_res = await db.execute(
        select(Company).where(Company.id == current_user["company_id"])
    )
    company = co_res.scalar_one_or_none()

    # Count employees with wages this year
    emp_count_res = await db.execute(
        select(func.count(func.distinct(PayRunItem.employee_id)))
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRunItem.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    emp_count = emp_count_res.scalar() or 0

    total_wages_res = await db.execute(
        select(func.sum(PayRunItem.gross_pay))
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRunItem.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
    )
    total_wages = float(total_wages_res.scalar() or 0)

    return {
        "year": year,
        "portal": "SSA Business Services Online (BSO)",
        "url": "https://www.ssa.gov/employer/",
        "deadline": f"January 31, {year + 1}",
        "your_data": {
            "company_name": company.name if company else "",
            "ein": company.ein if company else "Not set — add EIN in Company Settings",
            "employees_with_wages": emp_count,
            "total_wages": round(total_wages, 2),
            "w2_download_url": f"/w2/{year}/xml",
            "w2_data_url": f"/w2/{year}",
        },
        "steps": [
            {
                "step": 1,
                "title": "Register for BSO (first time only)",
                "url": "https://www.ssa.gov/employer/",
                "detail": (
                    "Go to ssa.gov/employer → click 'Business Services Online' → "
                    "'Register'. You need your EIN and company info. Registration "
                    "takes 5–10 minutes. You'll receive a PIN by mail within 2 weeks "
                    "— start early. If already registered, skip to step 3."
                ),
                "one_time": True,
            },
            {
                "step": 2,
                "title": "Activate your PIN",
                "url": "https://www.ssa.gov/employer/",
                "detail": (
                    "When your PIN arrives by mail, log into BSO and activate it. "
                    "Store it securely — you need it every year."
                ),
                "one_time": True,
            },
            {
                "step": 3,
                "title": "Download your W-2 EFW2 file",
                "url": f"/w2/{year}/xml",
                "detail": (
                    f"Download your W-2 data from PayrollOS: GET /w2/{year}/xml. "
                    "This produces an EFW2-format XML file. "
                    f"Your file covers {emp_count} employees, {round(total_wages,2)} total wages."
                ),
                "action": "download",
                "download_url": f"/w2/{year}/xml",
            },
            {
                "step": 4,
                "title": "Log into BSO and upload",
                "url": "https://www.ssa.gov/employer/",
                "detail": (
                    "Log into BSO → 'Report Wages to Social Security' → "
                    "'File W-2/W-2c Online' → select 'Upload Formatted Wage File'. "
                    "Upload the EFW2 XML file downloaded in step 3. "
                    "The system will validate your file and show any errors."
                ),
            },
            {
                "step": 5,
                "title": "Review and submit",
                "url": "https://www.ssa.gov/employer/",
                "detail": (
                    "Review the summary — verify employee count and total SS wages. "
                    "Click 'Submit'. You'll receive a receipt with a confirmation number. "
                    "Save this — it's your proof of filing."
                ),
            },
            {
                "step": 6,
                "title": "Send W-2s to employees",
                "detail": (
                    f"Mail or email W-2s to all employees by January 31, {year+1}. "
                    "PayrollOS paystub PDFs include YTD data. For official W-2 forms, "
                    "use the data from GET /w2/{year} and print on IRS W-2 paper stock "
                    "(available at office supply stores), or use a W-2 printing service."
                ),
            },
        ],
        "common_errors": [
            "Wrong EIN format — must be XX-XXXXXXX with dash",
            "Employee SSN doesn't match SSA records — verify with employee",
            "Box 1 wages don't match box 3 (SS wages) — check pre-tax deductions",
            "Missing state EIN — required for state W-2 boxes 15-17",
        ],
        "penalties": {
            "by_jan_31": "No penalty",
            "feb_1_to_mar_31": "$60 per form",
            "apr_1_to_aug_1": "$130 per form",
            "after_aug_1": "$330 per form",
            "intentional_disregard": "$660 per form",
        },
        "help": {
            "ssa_employer_helpline": "1-800-772-6270",
            "hours": "Monday–Friday, 7AM–7PM ET",
            "technical_help": "https://www.ssa.gov/employer/bsofaq.htm",
        },
    }


# ── IRS IRIS — 1099-NEC ────────────────────────────────────────
@router.get("/irs-iris/{year}")
async def irs_iris_guide(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Step-by-step guide + data for 1099-NEC submission via IRS IRIS.
    """
    # Count contractors requiring 1099
    from routes.contractors import ContractorPayment, Contractor
    count_res = await db.execute(
        select(
            func.count(func.distinct(ContractorPayment.contractor_id)),
            func.sum(ContractorPayment.amount),
        )
        .where(
            ContractorPayment.company_id == current_user["company_id"],
            ContractorPayment.tax_year == year,
        )
        .having(func.sum(ContractorPayment.amount) >= 600)
    )
    row = count_res.first()
    contractors_requiring = row[0] or 0 if row else 0
    total_1099_payments = float(row[1] or 0) if row else 0

    return {
        "year": year,
        "portal": "IRS IRIS — Information Returns Intake System",
        "url": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
        "deadline_to_irs": f"January 31, {year+1}",
        "deadline_to_contractor": f"January 31, {year+1}",
        "your_data": {
            "contractors_requiring_1099": contractors_requiring,
            "total_payments": round(total_1099_payments, 2),
            "threshold": 600,
            "report_url": f"/1099/report?year={year}",
            "xml_download_url": f"/1099/xml?year={year}",
        },
        "steps": [
            {
                "step": 1,
                "title": "Apply for a TCC (Transmitter Control Code) — first time",
                "url": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
                "detail": (
                    "Go to IRS IRIS portal → 'Apply for a TCC'. "
                    "You need your EIN, business contact info, and to confirm you're filing "
                    "on behalf of your own company (not a third-party filer). "
                    "IRS processes TCC applications in up to 45 days — apply by December 1. "
                    "You will receive a 5-character TCC code by email."
                ),
                "one_time": True,
                "allow_45_days": True,
            },
            {
                "step": 2,
                "title": "Log into IRIS and obtain API client ID",
                "url": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
                "detail": (
                    "After receiving your TCC, log into IRIS with your IRS.gov account. "
                    "Go to 'Create/Manage Your Information Returns' → generate an API client ID. "
                    "This enables direct API submission for future years."
                ),
                "one_time": True,
            },
            {
                "step": 3,
                "title": "Download your 1099-NEC data",
                "url": f"/1099/report?year={year}",
                "detail": (
                    f"Download your 1099 data from PayrollOS. "
                    f"You have {contractors_requiring} contractor(s) requiring 1099-NEC "
                    f"(paid $600+ in {year}), totaling ${total_1099_payments:,.2f}. "
                    "Download the XML: GET /1099/xml"
                ),
                "download_urls": {
                    "report": f"/1099/report?year={year}",
                    "xml": f"/1099/xml?year={year}",
                },
            },
            {
                "step": 4,
                "title": "Submit via IRIS web interface",
                "url": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
                "detail": (
                    "Log into IRIS → 'Upload' → select Form 1099-NEC → upload your XML file. "
                    "Alternatively use IRIS direct data entry for small volumes (< 10 forms). "
                    "IRIS validates the file and shows errors in real time."
                ),
            },
            {
                "step": 5,
                "title": "Send 1099-NEC copies to contractors",
                "detail": (
                    f"Mail or email Copy B of Form 1099-NEC to each contractor by January 31, {year+1}. "
                    "Contractors use this to file their own taxes. "
                    "You can print 1099 forms on plain paper (Copy B only) or use a 1099 printing service."
                ),
            },
        ],
        "important_notes": [
            "Only file for contractors paid $600+ in the calendar year",
            "Do NOT include W-2 employees on 1099 forms",
            "Independent contractors are responsible for their own self-employment tax (15.3%)",
            "No federal tax is withheld from contractor payments unless backup withholding applies",
            "Back-up withholding rate is 24% — applies if contractor has no TIN on file",
        ],
        "api_submission": {
            "available": True,
            "note": "After obtaining TCC + API client ID, IRIS supports direct API submission",
            "docs": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
            "format": "JSON or XML",
            "sandbox": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
        },
        "penalties": {
            "by_jan_31": "No penalty",
            "by_mar_31": "$60 per form",
            "after_aug_1": "$310 per form",
            "intentional_disregard": "$630 per form",
        },
        "help": {
            "irs_helpline": "1-866-455-7438",
            "hours": "Monday–Friday, 8:30AM–4:30PM ET",
            "iris_help": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
        },
    }


# ── State ACH tax payment portals ──────────────────────────────
@router.get("/state-ach/{year}")
async def state_ach_guide(
    year: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    State-by-state withholding payment portals, amounts owed, and instructions.
    """
    # Get withholding by state
    from sqlalchemy import text as sqlt
    state_res = await db.execute(
        select(
            Employee.state_code,
            func.sum(PayRunItem.state_income_tax).label("total_withheld"),
            func.sum(PayRunItem.suta_tax).label("total_suta"),
            func.count(func.distinct(PayRunItem.employee_id)).label("employees"),
        )
        .join(Employee, PayRunItem.employee_id == Employee.id)
        .join(PayRun, PayRunItem.pay_run_id == PayRun.id)
        .join(PayPeriod, PayRun.pay_period_id == PayPeriod.id)
        .where(
            PayRunItem.company_id == current_user["company_id"],
            PayRun.status == "completed",
            func.extract("year", PayPeriod.period_start) == year,
        )
        .group_by(Employee.state_code)
        .order_by(func.sum(PayRunItem.state_income_tax).desc())
    )
    state_rows = state_res.all()

    STATE_PORTALS = {
        "NY": {
            "name": "New York",
            "portal_name": "NY Online Services",
            "url": "https://www.tax.ny.gov/online/",
            "withholding_registration": "https://www.tax.ny.gov/pubs_and_bulls/tg_bulletins/wt/wt_employers.htm",
            "payment_url": "https://www.tax.ny.gov/pay/payroll_taxes/payroll_taxes.htm",
            "frequency": "semi-weekly or monthly (based on prior year liability)",
            "form": "NYS-1 (withholding) / NYS-45 (quarterly)",
            "suta_portal": "https://www.labor.ny.gov/ui/employerinfo/quarterly-payroll-reporting-responsibilities.shtm",
            "suta_rate": "2.1%–9.9% (new employer: 3.125%)",
            "phone": "518-485-6654",
        },
        "CA": {
            "name": "California",
            "portal_name": "EDD e-Services for Business",
            "url": "https://edd.ca.gov/en/payroll_taxes/e-Services_for_Business/",
            "withholding_registration": "https://www.edd.ca.gov/en/payroll_taxes/",
            "payment_url": "https://edd.ca.gov/en/payroll_taxes/e-Services_for_Business/",
            "frequency": "semi-weekly, monthly, or quarterly",
            "form": "DE 9 (quarterly) / DE 88 (deposit coupon)",
            "suta_portal": "https://edd.ca.gov/en/payroll_taxes/",
            "suta_rate": "1.5%–6.2% (new employer: 3.4% for 3 years)",
            "phone": "888-745-3886",
        },
        "TX": {
            "name": "Texas",
            "portal_name": "TWC Employer Portal",
            "url": "https://apps.twc.state.tx.us/UCS/logonPage.do",
            "withholding_registration": None,
            "payment_url": "https://apps.twc.state.tx.us/UCS/logonPage.do",
            "frequency": "quarterly",
            "form": "C-3 (quarterly wage report)",
            "suta_portal": "https://apps.twc.state.tx.us/UCS/logonPage.do",
            "suta_rate": "0.23%–6.23% (new employer: 2.7%)",
            "note": "No state income tax — SUTA only",
            "phone": "512-463-2699",
        },
        "FL": {
            "name": "Florida",
            "portal_name": "DEO Connect",
            "url": "https://connect.myflorida.com/employer",
            "payment_url": "https://connect.myflorida.com/employer",
            "frequency": "quarterly",
            "form": "RT-6",
            "suta_portal": "https://connect.myflorida.com/employer",
            "suta_rate": "0.1%–5.4% (new employer: 2.7%)",
            "note": "No state income tax — SUTA only",
            "phone": "877-846-8770",
        },
        "WA": {
            "name": "Washington",
            "portal_name": "SecureAccess Washington (SAW)",
            "url": "https://secure.esd.wa.gov/home/",
            "payment_url": "https://secure.esd.wa.gov/home/",
            "frequency": "quarterly",
            "form": "5208A (quarterly)",
            "suta_portal": "https://secure.esd.wa.gov/home/",
            "suta_rate": "0.27%–6.02%",
            "note": "No state income tax — SUTA + Paid Family Leave",
            "phone": "360-902-9360",
        },
        "IL": {
            "name": "Illinois",
            "portal_name": "MyTax Illinois",
            "url": "https://mytax.illinois.gov/_/",
            "payment_url": "https://mytax.illinois.gov/_/",
            "frequency": "semi-weekly or monthly",
            "form": "IL-941 (quarterly) / IL-501 (deposit)",
            "suta_portal": "https://www2.illinois.gov/ides/employers/",
            "suta_rate": "0.725%–7.625% (new employer: 3.175%)",
            "phone": "800-732-8866",
        },
        "MA": {
            "name": "Massachusetts",
            "portal_name": "MassTaxConnect",
            "url": "https://mtc.dor.state.ma.us/mtc/_/",
            "payment_url": "https://mtc.dor.state.ma.us/mtc/_/",
            "frequency": "semi-weekly, monthly, or quarterly",
            "form": "M-941 (monthly withholding)",
            "suta_portal": "https://uionline.detma.org/Claimant/Core/Login.ASPX",
            "suta_rate": "0.94%–14.37% (new employer: 2.42%)",
            "phone": "617-887-6367",
        },
        "NJ": {
            "name": "New Jersey",
            "portal_name": "NJDEP Online",
            "url": "https://www16.state.nj.us/NJ_ONLINE/",
            "payment_url": "https://www16.state.nj.us/NJ_ONLINE/",
            "frequency": "monthly or quarterly",
            "form": "NJ-927 (quarterly)",
            "suta_portal": "https://www.nj.gov/labor/employer-services/employer/",
            "suta_rate": "0.4%–5.4% (new employer: 2.8%)",
            "phone": "609-292-9292",
        },
        "GA": {
            "name": "Georgia",
            "portal_name": "Georgia Tax Center",
            "url": "https://gtc.dor.ga.gov/_/",
            "payment_url": "https://gtc.dor.ga.gov/_/",
            "frequency": "monthly or quarterly",
            "form": "G-7 (quarterly)",
            "suta_portal": "https://www.dol.state.ga.us/employers/unemployment/",
            "suta_rate": "0.04%–8.1% (new employer: 2.7%)",
            "phone": "404-417-4477",
        },
        "CO": {
            "name": "Colorado",
            "portal_name": "Revenue Online",
            "url": "https://www.colorado.gov/revenueonline/_/",
            "payment_url": "https://www.colorado.gov/revenueonline/_/",
            "frequency": "monthly or quarterly",
            "form": "DR 1094 (withholding) / UITR-1 (SUTA)",
            "suta_portal": "https://apps.cdle.state.co.us/myui/",
            "suta_rate": "0.71%–8.15% (new employer: 1.7%)",
            "phone": "303-205-8205",
        },
    }

    states_owed = []
    for row in state_rows:
        state = row.state_code
        if not state:
            continue
        portal = STATE_PORTALS.get(state, {
            "name": state,
            "portal_name": f"{state} Tax Portal",
            "url": f"https://www.google.com/search?q={state}+employer+withholding+tax+portal",
            "payment_url": None,
            "frequency": "check state DOR website",
            "form": "check state DOR website",
            "suta_portal": None,
            "phone": None,
        })

        withheld = float(row.total_withheld or 0)
        suta = float(row.total_suta or 0)

        states_owed.append({
            "state": state,
            "state_name": portal.get("name", state),
            "employees": row.employees,
            "state_income_tax_withheld": round(withheld, 2),
            "suta_owed": round(suta, 2),
            "total_owed": round(withheld + suta, 2),
            "portal": {
                "name": portal.get("portal_name", ""),
                "url": portal.get("url", ""),
                "payment_url": portal.get("payment_url"),
                "frequency": portal.get("frequency", ""),
                "form": portal.get("form", ""),
                "suta_portal": portal.get("suta_portal"),
                "suta_rate": portal.get("suta_rate", ""),
                "phone": portal.get("phone", ""),
                "note": portal.get("note", ""),
            },
        })

    total_state_liability = sum(s["total_owed"] for s in states_owed)

    return {
        "year": year,
        "total_state_tax_liability": round(total_state_liability, 2),
        "states": states_owed,
        "universal_steps": [
            {
                "step": 1,
                "action": "Register with each state's tax agency",
                "detail": "You must register in every state where you have employees. "
                          "Use each state's portal above. Most require your EIN, business address, "
                          "and first payroll date. Some states issue separate withholding and SUTA account numbers.",
            },
            {
                "step": 2,
                "action": "Set up ACH/EFT payment",
                "detail": "Most states require ACH payment for withholding over $15,000/year. "
                          "Log into each state portal and add your company bank account. "
                          "Some portals require a voided check for verification.",
            },
            {
                "step": 3,
                "action": "Submit quarterly wage reports",
                "detail": "Every state requires quarterly wage reports (usually Form SUI/SUTA). "
                          "PayrollOS exports CSV data per employee under Export → Time/Employee reports.",
            },
            {
                "step": 4,
                "action": "File annual reconciliation",
                "detail": "Most states require an annual reconciliation form comparing "
                          "payroll records to withholding deposits. Often due January 31.",
            },
        ],
        "deposit_schedules": {
            "note": "State deposit schedules mirror federal: semi-weekly if >$50k prior-year liability, else monthly",
            "irs_reference": "https://www.irs.gov/publications/p15",
        },
    }


# ── Filing deadlines ───────────────────────────────────────────
@router.get("/deadlines/{year}")
async def filing_deadlines(year: int):
    """All payroll tax filing deadlines for a given year."""
    return {
        "year": year,
        "federal": [
            {"date": f"Jan 31, {year}", "form": "Form 940 (FUTA annual return)",   "portal": "EFTPS", "url": "https://www.eftps.gov"},
            {"date": f"Jan 31, {year}", "form": "Form 941 Q4 (last year)",          "portal": "EFTPS / e-file", "url": "https://www.irs.gov/forms-pubs/about-form-941"},
            {"date": f"Jan 31, {year}", "form": "W-2 to employees",                 "portal": "Mail/email", "url": None},
            {"date": f"Jan 31, {year}", "form": "W-2 to SSA (e-file)",              "portal": "BSO", "url": "https://www.ssa.gov/employer/"},
            {"date": f"Jan 31, {year}", "form": "1099-NEC to contractors",           "portal": "Mail/email", "url": None},
            {"date": f"Jan 31, {year}", "form": "1099-NEC to IRS",                  "portal": "IRIS", "url": "https://www.irs.gov/filing/e-file-information-returns-with-iris"},
            {"date": f"Apr 30, {year}", "form": "Form 941 Q1",                      "portal": "EFTPS / e-file", "url": "https://www.irs.gov/forms-pubs/about-form-941"},
            {"date": f"Jul 31, {year}", "form": "Form 941 Q2",                      "portal": "EFTPS / e-file", "url": "https://www.irs.gov/forms-pubs/about-form-941"},
            {"date": f"Oct 31, {year}", "form": "Form 941 Q3",                      "portal": "EFTPS / e-file", "url": "https://www.irs.gov/forms-pubs/about-form-941"},
            {"date": f"Jan 31, {year+1}", "form": "Form 941 Q4 (this year)",        "portal": "EFTPS / e-file", "url": "https://www.irs.gov/forms-pubs/about-form-941"},
            {"date": f"Jan 31, {year+1}", "form": "W-2 / 1099 (this year wages)",   "portal": "BSO / IRIS", "url": None},
        ],
        "eftps_deposits": {
            "semi_weekly": "Deposit by Wed if payroll on Sat/Sun/Mon/Tue; by Fri if payroll on Wed/Thu/Fri",
            "monthly": "Deposit by the 15th of the following month",
            "rule": "If total 941 deposits in prior lookback period > $50,000: semi-weekly. Otherwise: monthly.",
            "url": "https://www.eftps.gov",
            "enrollment_url": "https://www.eftps.gov/eftps/direct/HomePageSetup.page",
        },
        "key_external_links": {
            "EFTPS (federal tax deposits)": "https://www.eftps.gov",
            "IRS IRIS (1099 e-filing)": "https://www.irs.gov/filing/e-file-information-returns-with-iris",
            "SSA BSO (W-2 filing)": "https://www.ssa.gov/employer/",
            "IRS Publication 15 (Circular E)": "https://www.irs.gov/publications/p15",
            "IRS Form 941": "https://www.irs.gov/forms-pubs/about-form-941",
            "IRS Form 940": "https://www.irs.gov/forms-pubs/about-form-940",
        },
    }
