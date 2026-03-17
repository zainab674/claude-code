"""
Core ORM models — single source of truth for all primary business entities.
"""
import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Numeric, Integer, Boolean, Date, DateTime, Text, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from database import Base


class Company(Base):
    __tablename__ = "companies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    ein = Column(String(20))
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(2))
    zip = Column(String(10))
    phone = Column(String(30))
    email = Column(String(255))
    website = Column(String(255))
    notification_email = Column(String(255))
    default_pay_frequency = Column(String(20), default="biweekly")
    default_state = Column(String(2))
    fiscal_year_start = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(20), default="viewer")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Employee(Base):
    __tablename__ = "employees"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255))
    phone = Column(String(30))
    ssn_encrypted = Column(String(500))
    date_of_birth = Column(Date)
    hire_date = Column(Date)
    termination_date = Column(Date)
    status = Column(String(20), default="active")
    job_title = Column(String(150))
    department = Column(String(100))
    manager_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    pay_type = Column(String(20), default="salary")
    pay_rate = Column(Numeric(12, 2), nullable=False)
    pay_frequency = Column(String(20), default="biweekly")
    filing_status = Column(String(30), default="single")
    state_code = Column(String(2), default="NY")
    federal_allowances = Column(Integer, default=0)
    exempt_from_federal = Column(Boolean, default=False)
    exempt_from_state = Column(Boolean, default=False)
    health_insurance_deduction = Column(Numeric(10, 2), default=0)
    dental_deduction = Column(Numeric(10, 2), default=0)
    vision_deduction = Column(Numeric(10, 2), default=0)
    retirement_401k_pct = Column(Numeric(5, 4), default=0)
    hsa_deduction = Column(Numeric(10, 2), default=0)
    fsa_deduction = Column(Numeric(10, 2), default=0)
    garnishment_amount = Column(Numeric(10, 2), default=0)
    other_post_tax_deduction = Column(Numeric(10, 2), default=0)
    address_line1 = Column(String(255))
    city = Column(String(100))
    state = Column(String(2))
    zip = Column(String(10))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class PayPeriod(Base):
    __tablename__ = "pay_periods"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    pay_date = Column(Date, nullable=False)
    frequency = Column(String(20), default="biweekly")
    status = Column(String(20), default="open")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PayRun(Base):
    __tablename__ = "pay_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    pay_period_id = Column(UUID(as_uuid=True), ForeignKey("pay_periods.id"))
    status = Column(String(20), default="draft")
    employee_count = Column(Integer, default=0)
    total_gross = Column(Numeric(14, 2), default=0)
    total_net = Column(Numeric(14, 2), default=0)
    total_employee_taxes = Column(Numeric(14, 2), default=0)
    total_employer_taxes = Column(Numeric(14, 2), default=0)
    total_deductions = Column(Numeric(14, 2), default=0)
    notes = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PayRunItem(Base):
    __tablename__ = "pay_run_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pay_run_id = Column(UUID(as_uuid=True), ForeignKey("pay_runs.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"))
    regular_hours = Column(Numeric(8, 2), default=0)
    overtime_hours = Column(Numeric(8, 2), default=0)
    regular_pay = Column(Numeric(12, 2), default=0)
    overtime_pay = Column(Numeric(12, 2), default=0)
    bonus_pay = Column(Numeric(12, 2), default=0)
    reimbursement = Column(Numeric(12, 2), default=0)
    gross_pay = Column(Numeric(12, 2), default=0)
    taxable_gross = Column(Numeric(12, 2), default=0)
    federal_income_tax = Column(Numeric(10, 2), default=0)
    state_income_tax = Column(Numeric(10, 2), default=0)
    social_security_tax = Column(Numeric(10, 2), default=0)
    medicare_tax = Column(Numeric(10, 2), default=0)
    additional_medicare_tax = Column(Numeric(10, 2), default=0)
    total_employee_taxes = Column(Numeric(10, 2), default=0)
    employer_social_security = Column(Numeric(10, 2), default=0)
    employer_medicare = Column(Numeric(10, 2), default=0)
    futa_tax = Column(Numeric(10, 2), default=0)
    suta_tax = Column(Numeric(10, 2), default=0)
    total_employer_taxes = Column(Numeric(10, 2), default=0)
    health_insurance = Column(Numeric(10, 2), default=0)
    dental_insurance = Column(Numeric(10, 2), default=0)
    vision_insurance = Column(Numeric(10, 2), default=0)
    retirement_401k = Column(Numeric(10, 2), default=0)
    hsa = Column(Numeric(10, 2), default=0)
    fsa = Column(Numeric(10, 2), default=0)
    total_pretax_deductions = Column(Numeric(10, 2), default=0)
    garnishment = Column(Numeric(10, 2), default=0)
    other_post_tax = Column(Numeric(10, 2), default=0)
    total_posttax_deductions = Column(Numeric(10, 2), default=0)
    net_pay = Column(Numeric(12, 2), default=0)
    ytd_gross = Column(Numeric(14, 2), default=0)
    ytd_net = Column(Numeric(14, 2), default=0)
    ytd_federal = Column(Numeric(12, 2), default=0)
    ytd_state = Column(Numeric(12, 2), default=0)
    ytd_ss = Column(Numeric(12, 2), default=0)
    ytd_medicare = Column(Numeric(12, 2), default=0)
    ytd_401k = Column(Numeric(12, 2), default=0)
    ytd_ss_wages = Column(Numeric(14, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Paystub(Base):
    __tablename__ = "paystubs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pay_run_id = Column(UUID(as_uuid=True), ForeignKey("pay_runs.id", ondelete="CASCADE"))
    pay_run_item_id = Column(UUID(as_uuid=True), ForeignKey("pay_run_items.id", ondelete="CASCADE"))
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    pdf_path = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    entry_date = Column(Date, nullable=False)
    clock_in = Column(DateTime(timezone=True))
    clock_out = Column(DateTime(timezone=True))
    regular_hours = Column(Numeric(6, 2), default=0)
    overtime_hours = Column(Numeric(6, 2), default=0)
    break_minutes = Column(Integer, default=0)
    status = Column(String(20), default="pending")
    notes = Column(Text)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_email = Column(String(255))
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(String(100))
    ip_address = Column(String(45))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
