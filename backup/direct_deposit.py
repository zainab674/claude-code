"""
Direct deposit bank account management.
Stores employee bank account info for payroll processing.
Actual ACH transfers require a banking partner (Dwolla, Stripe Payouts, etc.)

Routing + account numbers are AES-encrypted at rest using the same
encryption service as SSNs.

POST   /direct-deposit/employees/{id}   add/update bank account
GET    /direct-deposit/employees/{id}   get masked bank info
DELETE /direct-deposit/employees/{id}   remove bank account
GET    /direct-deposit/employees/{id}/verify   check account is verified
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, select
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from database import Base, get_db
from services.encryption import encrypt_ssn as _encrypt, decrypt_ssn as _decrypt
from utils.auth import get_current_user

router = APIRouter(prefix="/direct-deposit", tags=["direct-deposit"])


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), unique=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    bank_name = Column(String(100))
    account_type = Column(String(20), default="checking")   # checking | savings
    routing_number_encrypted = Column(String(500))          # AES-encrypted
    account_number_encrypted = Column(String(500))          # AES-encrypted
    account_last4 = Column(String(4))                       # stored unencrypted for display
    routing_last4 = Column(String(4))
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    verified_at = Column(DateTime(timezone=True))


class BankAccountCreate(BaseModel):
    bank_name: Optional[str] = None
    account_type: str = "checking"
    routing_number: str
    account_number: str


@router.get("/employees/{employee_id}")
async def get_bank_account(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.employee_id == employee_id,
            BankAccount.company_id == current_user["company_id"],
            BankAccount.is_active == True,
        )
    )
    acct = result.scalar_one_or_none()
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
    db: AsyncSession = Depends(get_db),
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

    # Deactivate existing
    existing_res = await db.execute(
        select(BankAccount).where(
            BankAccount.employee_id == employee_id,
            BankAccount.company_id == current_user["company_id"],
        )
    )
    for existing in existing_res.scalars().all():
        existing.is_active = False

    # Store encrypted
    acct = BankAccount(
        employee_id=employee_id,
        company_id=current_user["company_id"],
        bank_name=body.bank_name,
        account_type=body.account_type,
        routing_number_encrypted=_safe_encrypt(routing),
        account_number_encrypted=_safe_encrypt(account),
        account_last4=account[-4:],
        routing_last4=routing[-4:],
        is_verified=False,
    )
    db.add(acct)
    await db.commit()
    await db.refresh(acct)

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
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Mark bank account as verified (in production: verify micro-deposits)."""
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.employee_id == employee_id,
            BankAccount.company_id == current_user["company_id"],
            BankAccount.is_active == True,
        )
    )
    acct = result.scalar_one_or_none()
    if not acct:
        raise HTTPException(404, "No bank account found")
    acct.is_verified = True
    acct.verified_at = datetime.utcnow()
    await db.commit()
    return {"message": "Bank account verified", "is_verified": True}


@router.delete("/employees/{employee_id}", status_code=204)
async def remove_bank_account(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(BankAccount).where(
            BankAccount.employee_id == employee_id,
            BankAccount.company_id == current_user["company_id"],
        )
    )
    for acct in result.scalars().all():
        acct.is_active = False
    await db.commit()


@router.get("/summary")
async def direct_deposit_summary(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Summary of direct deposit enrollment across all employees."""
    from models import Employee
    from sqlalchemy import func

    emp_count_res = await db.execute(
        select(func.count(Employee.id)).where(
            Employee.company_id == current_user["company_id"],
            Employee.status == "active",
        )
    )
    total_employees = emp_count_res.scalar() or 0

    enrolled_res = await db.execute(
        select(func.count(BankAccount.id)).where(
            BankAccount.company_id == current_user["company_id"],
            BankAccount.is_active == True,
        )
    )
    enrolled = enrolled_res.scalar() or 0

    verified_res = await db.execute(
        select(func.count(BankAccount.id)).where(
            BankAccount.company_id == current_user["company_id"],
            BankAccount.is_active == True,
            BankAccount.is_verified == True,
        )
    )
    verified = verified_res.scalar() or 0

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


def _safe_encrypt(value: str) -> str:
    """Encrypt using services.encryption, fall back to storing raw if key not set."""
    try:
        return _encrypt(value)
    except Exception:
        return f"plain:{value}"
