import csv
import io
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, Response, HTTPException
from models import PayRun, PayRunItem, PayPeriod, Company
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(prefix="/journal", tags=["journal"])

# Chart of accounts — customize to match your accounting system
ACCOUNTS = {
    "wage_expense":          ("6100", "Wage Expense"),
    "payroll_tax_expense":   ("6200", "Payroll Tax Expense"),
    "benefits_expense":      ("6300", "Employee Benefits Expense"),
    "federal_tax_payable":   ("2100", "Federal Income Tax Payable"),
    "ss_tax_payable":        ("2110", "Social Security Tax Payable"),
    "medicare_payable":      ("2120", "Medicare Tax Payable"),
    "state_tax_payable":     ("2130", "State Income Tax Payable"),
    "benefits_payable":      ("2200", "Employee Benefits Payable"),
    "retirement_payable":    ("2210", "401(k) Payable"),
    "garnishment_payable":   ("2300", "Garnishments Payable"),
    "futa_payable":          ("2400", "FUTA Tax Payable"),
    "suta_payable":          ("2410", "SUTA Tax Payable"),
    "accrued_wages":         ("2500", "Accrued Wages Payable"),
}


@router.get("/{run_id}")
async def get_journal_entries(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    run, items, period, company = await _load(run_id, current_user["company_id"])
    entries = _build_entries(run, items, period, company)
    total_debits = sum(e["debit"] for e in entries)
    total_credits = sum(e["credit"] for e in entries)
    return {
        "pay_run_id": run_id,
        "period": f"{period.period_start} – {period.period_end}" if period else "",
        "pay_date": str(period.pay_date) if period else "",
        "total_debits": round(total_debits, 2),
        "total_credits": round(total_credits, 2),
        "balanced": abs(total_debits - total_credits) < 0.02,
        "entries": entries,
        "company": company.name if company else "",
    }


@router.get("/{run_id}/csv")
async def download_journal_csv(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    run, items, period, company = await _load(run_id, current_user["company_id"])
    entries = _build_entries(run, items, period, company)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["date","account_code","account_name","description","debit","credit","department"])
    writer.writeheader()
    writer.writerows(entries)

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="journal-{run_id[:8]}.csv"'},
    )


@router.get("/{run_id}/qbo")
async def download_qbo_iif(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    """QuickBooks IIF format for direct import."""
    run, items, period, company = await _load(run_id, current_user["company_id"])
    entries = _build_entries(run, items, period, company)

    lines = [
        "!TRNS\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tDOCSNUM\tMEMO",
        "!SPL\tTRNSTYPE\tDATE\tACCNT\tNAME\tAMOUNT\tMEMO",
        "!ENDTRNS",
    ]

    pay_date = str(period.pay_date) if period else ""
    ref = f"PAY-{run_id[:8].upper()}"
    memo = f"Payroll {pay_date}"

    # First line: opening TRNS (net wages out)
    net = sum(e["credit"] for e in entries if e["account_code"] == ACCOUNTS["accrued_wages"][0])
    lines.append(f"TRNS\tGENERAL JOURNAL\t{pay_date}\t{ACCOUNTS['accrued_wages'][1]}\t\t-{net:.2f}\t{ref}\t{memo}")

    for e in entries:
        if e["account_code"] == ACCOUNTS["accrued_wages"][0]:
            continue
        amount = e["debit"] if e["debit"] > 0 else -e["credit"]
        lines.append(f"SPL\tGENERAL JOURNAL\t{pay_date}\t{e['account_name']}\t\t{amount:.2f}\t{e['description']}")

    lines.append("ENDTRNS")

    return Response(
        content="\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="payroll-{ref}.iif"'},
    )


# ── Builder ────────────────────────────────────────────────────
def _build_entries(run, items, period, company):
    pay_date = str(period.pay_date) if period else ""

    # Aggregate from all items
    gross = float(run.total_gross or 0)
    net = float(run.total_net or 0)
    fed = sum(float(i.federal_income_tax or 0) for i in items)
    ss_emp = sum(float(i.social_security_tax or 0) for i in items)
    med_emp = sum(float(i.medicare_tax or 0) for i in items)
    state = sum(float(i.state_income_tax or 0) for i in items)
    health = sum(float(i.health_insurance or 0) + float(i.dental_insurance or 0) + float(i.vision_insurance or 0) for i in items)
    retire = sum(float(i.retirement_401k or 0) for i in items)
    hsa = sum(float(i.hsa or 0) for i in items)
    garnish = sum(float(i.garnishment or 0) for i in items)
    ss_er = sum(float(i.employer_social_security or 0) for i in items)
    med_er = sum(float(i.employer_medicare or 0) for i in items)
    futa = sum(float(i.futa_tax or 0) for i in items)
    suta = sum(float(i.suta_tax or 0) for i in items)
    er_taxes = ss_er + med_er + futa + suta

    def e(acct_key, desc, debit=0.0, credit=0.0, dept=""):
        code, name = ACCOUNTS[acct_key]
        return {
            "date": pay_date,
            "account_code": code,
            "account_name": name,
            "description": desc,
            "debit": round(debit, 2),
            "credit": round(credit, 2),
            "department": dept,
        }

    entries = [
        # ── Employee side ──────────────────────────────────────
        e("wage_expense",        f"Gross wages – {pay_date}",         debit=gross),
        e("federal_tax_payable", "Federal income tax withheld",        credit=fed),
        e("ss_tax_payable",      "Employee social security withheld",  credit=ss_emp),
        e("medicare_payable",    "Employee Medicare withheld",         credit=med_emp),
        e("state_tax_payable",   "State income tax withheld",          credit=state),
    ]
    if health:
        entries.append(e("benefits_payable", "Health/dental/vision premiums", credit=health))
    if retire:
        entries.append(e("retirement_payable", "401(k) contributions",         credit=retire))
    if hsa:
        entries.append(e("benefits_payable",   "HSA contributions",            credit=hsa))
    if garnish:
        entries.append(e("garnishment_payable", "Wage garnishments",            credit=garnish))
    entries.append(e("accrued_wages", f"Net wages payable – {pay_date}",       credit=net))

    # ── Employer tax side ──────────────────────────────────────
    if er_taxes > 0:
        entries.append(e("payroll_tax_expense", "Employer payroll taxes",       debit=er_taxes))
    if ss_er:
        entries.append(e("ss_tax_payable",   "Employer SS tax payable",         credit=ss_er))
    if med_er:
        entries.append(e("medicare_payable", "Employer Medicare payable",       credit=med_er))
    if futa:
        entries.append(e("futa_payable",     "FUTA payable",                    credit=futa))
    if suta:
        entries.append(e("suta_payable",     "SUTA payable",                    credit=suta))

    return [x for x in entries if x["debit"] > 0 or x["credit"] > 0]


async def _load(run_id: str, company_id: str):
    run_uuid = UUID(run_id)
    company_uuid = UUID(company_id)

    run = await PayRun.find_one(PayRun.id == run_uuid, PayRun.company_id == company_uuid)
    if not run:
        raise HTTPException(404, "Pay run not found")

    items = await PayRunItem.find(PayRunItem.pay_run_id == run_uuid).to_list()
    period = await PayPeriod.find_one(PayPeriod.id == run.pay_period_id)
    company = await Company.find_one(Company.id == company_uuid)

    return run, items, period, company
