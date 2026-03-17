import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import BankAccount, Employee
from utils.auth import get_current_user
from utils.encryption import encrypt_data, decrypt_data
from uuid import UUID

router = APIRouter(prefix="/direct-deposit", tags=["direct-deposit"])


# ── Schemas ────────────────────────────────────────────────────
class BankAccountCreate(BaseModel):
    bank_name: Optional[str] = None
    account_type: str = "checking"
    routing_number: str
    account_number: str


# ── Routes ─────────────────────────────────────────────────────
@router.get("/employees/{employee_id}")
async def get_bank_account(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    acct = await BankAccount.find_one(
        BankAccount.employee_id == UUID(employee_id),
        BankAccount.company_id == current_user["company_id"],
        BankAccount.is_active == True,
    )
    if not acct:
        return {"has_direct_deposit": False}
    return {
        "has_direct_deposit": True,
        "bank_name": acct.bank_name,
        "account_type": acct.account_type,
        "routing_last4": acct.routing_last4,
        "account_last4": acct.account_last4,
        "account_display": f"****{acct.account_last4}",
        "routing_display": f"****{acct.routing_last4}",
        "is_verified": acct.is_verified,
        "added_at": str(acct.added_at),
    }


@router.post("/employees/{employee_id}", status_code=201)
async def add_bank_account(
    employee_id: str,
    body: BankAccountCreate,
    current_user: dict = Depends(get_current_user),
):
    # Validate routing number (9 digits, ABA checksum)
    routing = body.routing_number.strip().replace("-", "")
    if not routing.isdigit() or len(routing) != 9:
        raise HTTPException(400, "Routing number must be 9 digits")
    if not _aba_checksum(routing):
        raise HTTPException(400, "Invalid routing number (ABA checksum failed)")

    account = body.account_number.strip().replace("-", "").replace(" ", "")
    if not account.isdigit() or not (4 <= len(account) <= 17):
        raise HTTPException(400, "Account number must be 4-17 digits")

    company_id = current_user["company_id"]
    emp_uuid = UUID(employee_id)

    # Deactivate existing
    existing_accounts = await BankAccount.find(
        BankAccount.employee_id == emp_uuid,
        BankAccount.company_id == company_id,
        BankAccount.is_active == True,
    ).to_list()
    for existing in existing_accounts:
        existing.is_active = False
        await existing.save()

    # Store encrypted
    acct = BankAccount(
        employee_id=emp_uuid,
        company_id=company_id,
        bank_name=body.bank_name,
        account_type=body.account_type,
        routing_number_encrypted=encrypt_data(routing),
        account_number_encrypted=encrypt_data(account),
        account_last4=account[-4:],
        routing_last4=routing[-4:],
        is_verified=False,
    )
    await acct.insert()

    return {
        "message": "Bank account saved",
        "account_display": f"****{acct.account_last4}",
        "routing_display": f"****{acct.routing_last4}",
        "account_type": acct.account_type,
        "is_verified": False,
        "note": "Bank account stored securely. Micro-deposit verification will be sent.",
    }


@router.put("/employees/{employee_id}/verify")
async def verify_bank_account(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark bank account as verified."""
    acct = await BankAccount.find_one(
        BankAccount.employee_id == UUID(employee_id),
        BankAccount.company_id == current_user["company_id"],
        BankAccount.is_active == True,
    )
    if not acct:
        raise HTTPException(404, "No bank account found")
    acct.is_verified = True
    acct.verified_at = datetime.utcnow()
    await acct.save()
    return {"message": "Bank account verified", "is_verified": True}


@router.delete("/employees/{employee_id}", status_code=204)
async def remove_bank_account(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    existing_accounts = await BankAccount.find(
        BankAccount.employee_id == UUID(employee_id),
        BankAccount.company_id == current_user["company_id"],
    ).to_list()
    for acct in existing_accounts:
        acct.is_active = False
        await acct.save()


@router.get("/summary")
async def direct_deposit_summary(
    current_user: dict = Depends(get_current_user),
):
    """Summary of direct deposit enrollment across all employees."""
    company_id = current_user["company_id"]
    
    total_employees = await Employee.find(
        Employee.company_id == company_id,
        Employee.status == "active",
    ).count()

    enrolled = await BankAccount.find(
        BankAccount.company_id == company_id,
        BankAccount.is_active == True,
    ).count()

    verified = await BankAccount.find(
        BankAccount.company_id == company_id,
        BankAccount.is_active == True,
        BankAccount.is_verified == True,
    ).count()

    return {
        "total_employees": total_employees,
        "enrolled": enrolled,
        "verified": verified,
        "not_enrolled": total_employees - enrolled,
        "enrollment_pct": round(enrolled / total_employees * 100, 1) if total_employees else 0,
    }


def _aba_checksum(routing: str) -> bool:
    """Validate 9-digit ABA routing number via checksum."""
    try:
        d = [int(c) for c in routing]
        checksum = (
            3 * (d[0] + d[3] + d[6]) +
            7 * (d[1] + d[4] + d[7]) +
            1 * (d[2] + d[5] + d[8])
        )
        return checksum % 10 == 0
    except Exception:
        return False
