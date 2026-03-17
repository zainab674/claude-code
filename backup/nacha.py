"""
NACHA ACH file generator.
Produces a standards-compliant NACHA file for bank direct deposit submission.

NACHA format: fixed-width 94-character records
  File Header (1)
  Company Batch Header (5)
  Entry Detail records (6)
  Batch Control (8)
  File Control (9)

POST /nacha/generate      → generate NACHA file for a pay run
GET  /nacha/preview/{id}  → preview entries before generating
GET  /nacha/download/{id} → download .ach file

After generating:
  1. Download the .ach file
  2. Log into your bank's ACH origination portal
  3. Upload the file
  4. Bank processes on the pay date
"""
import os
import uuid
import hashlib
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from database import get_db
from models import PayRun, PayRunItem, PayPeriod, Employee, Company
from utils.auth import get_current_user

router = APIRouter(prefix="/nacha", tags=["nacha"])

NACHA_DIR = os.getenv("NACHA_DIR", "./nacha_files")

# Standard Codes
CHECKING = "22"   # Automated Deposit to Checking
SAVINGS  = "32"   # Automated Deposit to Savings


class NachaRequest(BaseModel):
    pay_run_id: str
    effective_entry_date: Optional[date] = None   # defaults to pay_date
    company_discretionary_data: str = ""


# ── NACHA record builders ──────────────────────────────────────
def _pad(s: str, length: int, char: str = " ", right: bool = False) -> str:
    s = str(s)[:length]
    return s.rjust(length, char) if right else s.ljust(length, char)

def _file_header(routing: str, company_id: str, file_creation_date: str, file_creation_time: str) -> str:
    """Record type 1 — 94 chars"""
    return (
        "1"                    # Record type
        + "01"                 # Priority code
        + _pad(" " + routing[:8], 10)  # Immediate destination (leading space + routing)
        + _pad(company_id, 10)          # Immediate origin
        + file_creation_date            # File creation date YYMMDD
        + file_creation_time            # HHMM
        + "A"                           # File ID modifier
        + "094"                         # Record size
        + "10"                          # Blocking factor
        + "1"                           # Format code
        + _pad("PAYROLLOS ACH", 23)     # Immediate destination name
        + _pad("PAYROLLOS", 23)         # Immediate origin name
        + "        "                    # Reference code (8 spaces)
    )

def _batch_header(company_name: str, company_id: str, sec_code: str,
                  description: str, effective_date: str, batch_number: int) -> str:
    """Record type 5 — 94 chars"""
    return (
        "5"                             # Record type
        + "200"                         # Service class (200 = mixed credits/debits)
        + _pad(company_name, 16)        # Company name
        + _pad("", 20)                  # Company discretionary data
        + _pad(company_id, 10)          # Company identification (EIN or 10-char)
        + sec_code                      # Standard entry class code (PPD)
        + _pad(description, 10)         # Company entry description
        + "      "                      # Company descriptive date (6 spaces)
        + effective_date                # Effective entry date YYMMDD
        + "   "                         # Settlement date (bank fills)
        + "1"                           # Originator status
        + "0" * 8                       # Originating DFI routing (8 digits)
        + _pad(str(batch_number), 7, "0", right=True)  # Batch number
    )

def _entry_detail(routing: str, account: str, amount_cents: int, name: str,
                  trace_num: str, account_type: str = CHECKING) -> str:
    """Record type 6 — 94 chars"""
    dfi_routing = routing[:8]              # First 8 digits of routing
    check_digit  = routing[8] if len(routing) > 8 else "0"
    return (
        "6"                              # Record type
        + account_type                   # Transaction code (22=checking, 32=savings)
        + dfi_routing                    # Receiving DFI routing (8 digits)
        + check_digit                    # Check digit
        + _pad(account, 17)             # DFI account number
        + _pad(str(amount_cents), 10, "0", right=True)  # Amount in cents
        + _pad("", 15)                  # Individual identification number
        + _pad(name, 22)               # Individual name
        + "  "                          # Discretionary data
        + "0"                           # Addenda record indicator
        + trace_num                     # Trace number (15 chars)
    )

def _batch_control(service_class: str, entry_count: int, entry_hash: str,
                   total_debit: int, total_credit: int, company_id: str,
                   batch_number: int) -> str:
    """Record type 8 — 94 chars"""
    return (
        "8"                             # Record type
        + service_class                 # Service class
        + _pad(str(entry_count), 6, "0", right=True)   # Entry/addenda count
        + _pad(entry_hash, 10, "0", right=True)         # Entry hash (sum of routing 8-digits)
        + _pad(str(total_debit), 12, "0", right=True)   # Total debit
        + _pad(str(total_credit), 12, "0", right=True)  # Total credit
        + _pad(company_id, 10)         # Company identification
        + " " * 25                     # Message authentication code
        + " " * 6                      # Reserved
        + "0" * 8                      # Originating DFI ID
        + _pad(str(batch_number), 7, "0", right=True)   # Batch number
    )

def _file_control(batch_count: int, block_count: int, entry_addenda_count: int,
                  entry_hash: str, total_debit: int, total_credit: int) -> str:
    """Record type 9 — 94 chars"""
    return (
        "9"                            # Record type
        + _pad(str(batch_count), 6, "0", right=True)        # Batch count
        + _pad(str(block_count), 6, "0", right=True)         # Block count
        + _pad(str(entry_addenda_count), 8, "0", right=True) # Entry/addenda count
        + _pad(entry_hash, 10, "0", right=True)              # Entry hash
        + _pad(str(total_debit), 12, "0", right=True)        # Total debit
        + _pad(str(total_credit), 12, "0", right=True)       # Total credit
        + " " * 39                     # Reserved
    )

def _blocking_lines(current_line_count: int) -> str:
    """NACHA files must be in blocks of 10. Pad with 9s."""
    remainder = current_line_count % 10
    if remainder == 0:
        return ""
    needed = 10 - remainder
    return "\n".join(["9" * 94] * needed)


# ── Routes ─────────────────────────────────────────────────────
@router.post("/generate")
async def generate_nacha(
    body: NachaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    run, items, period, company = await _load(db, body.pay_run_id, current_user["company_id"])
    effective_date = body.effective_entry_date or (period.pay_date if period else date.today())

    # Load bank accounts
    from routes.direct_deposit import BankAccount
    bank_res = await db.execute(
        select(BankAccount).where(
            BankAccount.company_id == current_user["company_id"],
            BankAccount.is_active == True,
        )
    )
    banks = {str(b.employee_id): b for b in bank_res.scalars().all()}

    # Build entry list
    entries = []
    skipped = []
    for item in items:
        emp_res = await db.execute(select(Employee).where(Employee.id == item.employee_id))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            continue

        bank = banks.get(str(item.employee_id))
        if not bank or not bank.is_verified:
            skipped.append({"employee_id": str(item.employee_id),
                            "name": f"{emp.first_name} {emp.last_name}",
                            "reason": "no verified bank account"})
            continue

        try:
            from services.encryption import decrypt_ssn as decrypt
            routing = decrypt(bank.routing_number_encrypted).replace("-","").replace(" ","")
            account = decrypt(bank.account_number_encrypted).replace("-","").replace(" ","")
        except Exception:
            skipped.append({"employee_id": str(item.employee_id),
                            "name": f"{emp.first_name} {emp.last_name}",
                            "reason": "could not decrypt bank info"})
            continue

        amount_cents = int(round(float(item.net_pay or 0) * 100))
        if amount_cents <= 0:
            skipped.append({"employee_id": str(item.employee_id),
                            "name": f"{emp.first_name} {emp.last_name}",
                            "reason": "net pay is zero"})
            continue

        acct_type = SAVINGS if (bank.account_type or "checking").lower() == "savings" else CHECKING
        entries.append({
            "routing": routing,
            "account": account,
            "amount_cents": amount_cents,
            "name": f"{emp.last_name} {emp.first_name}"[:22],
            "account_type": acct_type,
        })

    if not entries:
        return {
            "success": False,
            "message": "No employees with verified bank accounts found",
            "skipped": skipped,
        }

    # Build NACHA content
    now = datetime.utcnow()
    file_date  = now.strftime("%y%m%d")
    file_time  = now.strftime("%H%M")
    eff_date   = effective_date.strftime("%y%m%d")
    company_id = (company.ein or "0000000000").replace("-","")[:10].ljust(10)
    routing_origin = "0" * 9   # use 0s when no bank routing — bank fills in
    batch_num  = 1

    lines = []
    lines.append(_file_header(routing_origin, company_id, file_date, file_time))
    lines.append(_batch_header(
        company_name=(company.name or "COMPANY")[:16],
        company_id=company_id,
        sec_code="PPD",   # Prearranged Payment and Deposit
        description="PAYROLL",
        effective_date=eff_date,
        batch_number=batch_num,
    ))

    routing_hash_sum = 0
    total_credit_cents = 0
    for i, e in enumerate(entries):
        trace = f"{'0'*8}{str(i+1).zfill(7)}"
        lines.append(_entry_detail(
            routing=e["routing"],
            account=e["account"],
            amount_cents=e["amount_cents"],
            name=e["name"],
            trace_num=trace,
            account_type=e["account_type"],
        ))
        routing_hash_sum += int(e["routing"][:8])
        total_credit_cents += e["amount_cents"]

    # Batch control
    batch_hash = str(routing_hash_sum)[-10:]   # last 10 digits
    lines.append(_batch_control(
        service_class="220",      # credits only
        entry_count=len(entries),
        entry_hash=batch_hash,
        total_debit=0,
        total_credit=total_credit_cents,
        company_id=company_id,
        batch_number=batch_num,
    ))

    # File control
    total_lines = len(lines) + 1   # +1 for file control
    block_count = -(-total_lines // 10)   # ceiling division
    lines.append(_file_control(
        batch_count=1,
        block_count=block_count,
        entry_addenda_count=len(entries),
        entry_hash=batch_hash,
        total_debit=0,
        total_credit=total_credit_cents,
    ))

    # Pad to block of 10
    pad = _blocking_lines(len(lines))
    if pad:
        lines.append(pad)

    nacha_content = "\r\n".join(lines)   # NACHA requires CRLF

    # Save to disk
    os.makedirs(NACHA_DIR, exist_ok=True)
    file_id = str(uuid.uuid4())
    filename = f"payroll-{body.pay_run_id[:8]}-{file_date}.ach"
    filepath = os.path.join(NACHA_DIR, filename)
    with open(filepath, "w") as f:
        f.write(nacha_content)

    total_dollars = total_credit_cents / 100
    return {
        "success": True,
        "file_id": file_id,
        "filename": filename,
        "filepath": filepath,
        "employee_count": len(entries),
        "total_amount": round(total_dollars, 2),
        "effective_date": str(effective_date),
        "skipped": skipped,
        "download_url": f"/nacha/download/{filename}",
        "next_steps": [
            "Download the .ach file below",
            "Log into your bank's ACH origination portal",
            "Upload the file (usually under Payments > ACH > Upload File)",
            "Confirm the effective date matches your pay date",
            "Approve the batch — funds will transfer on the effective date",
        ],
    }


@router.get("/download/{filename}")
async def download_nacha(
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    filepath = os.path.join(NACHA_DIR, filename)
    if not os.path.exists(filepath) or ".." in filename:
        raise HTTPException(404, "File not found")
    content = open(filepath).read()
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/preview/{pay_run_id}")
async def preview_nacha(
    pay_run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Preview which employees will be included in the NACHA file."""
    run, items, period, company = await _load(db, pay_run_id, current_user["company_id"])

    from routes.direct_deposit import BankAccount
    bank_res = await db.execute(
        select(BankAccount).where(
            BankAccount.company_id == current_user["company_id"],
            BankAccount.is_active == True,
        )
    )
    banks = {str(b.employee_id): b for b in bank_res.scalars().all()}

    will_include = []
    will_skip = []
    total = 0.0

    for item in items:
        emp_res = await db.execute(select(Employee).where(Employee.id == item.employee_id))
        emp = emp_res.scalar_one_or_none()
        if not emp:
            continue
        bank = banks.get(str(item.employee_id))
        net = float(item.net_pay or 0)
        if bank and bank.is_verified and net > 0:
            will_include.append({
                "name": f"{emp.first_name} {emp.last_name}",
                "account_display": f"****{bank.account_last4}",
                "bank_name": bank.bank_name,
                "net_pay": net,
            })
            total += net
        else:
            reason = "no bank account" if not bank else ("not verified" if not bank.is_verified else "zero net pay")
            will_skip.append({"name": f"{emp.first_name} {emp.last_name}", "reason": reason})

    return {
        "will_include": will_include,
        "will_skip": will_skip,
        "total_amount": round(total, 2),
        "ready_to_generate": len(will_include) > 0,
    }


async def _load(db, run_id, company_id):
    run_res = await db.execute(
        select(PayRun).where(PayRun.id == run_id, PayRun.company_id == company_id)
    )
    run = run_res.scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Pay run not found")
    items_res = await db.execute(select(PayRunItem).where(PayRunItem.pay_run_id == run_id))
    items = items_res.scalars().all()
    period_res = await db.execute(select(PayPeriod).where(PayPeriod.id == run.pay_period_id))
    period = period_res.scalar_one_or_none()
    co_res = await db.execute(select(Company).where(Company.id == company_id))
    company = co_res.scalar_one_or_none()
    return run, items, period, company
