"""
Unified ORM models — single source of truth for all business entities.
Migrated to Beanie (MongoDB).
Consolidated from various route files for clean architecture.
"""
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Annotated
from decimal import Decimal
from pydantic import Field, ConfigDict, UUID4
from beanie import Document, Indexed, init_beanie
from beanie.odm.custom_types.decimal import DecimalAnnotation


# ── Core ────────────────────────────────────────────────────────
class Company(Document):
    # Beanie handles 'id' as '_id' automatically.
    # We use UUID4 as the type for 'id'.
    id: UUID4 = Field(default_factory=uuid.uuid4)
    name: str = Field(max_length=200)
    ein: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    notification_email: Optional[str] = None
    default_pay_frequency: str = "biweekly"
    default_state: Optional[str] = None
    fiscal_year_start: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "companies"


class User(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    email: Annotated[str, Indexed(unique=True)]
    password_hash: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "viewer"
    is_active: bool = True
    last_login: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"


class Employee(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    ssn_encrypted: Optional[str] = None
    date_of_birth: Optional[date] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    status: str = "active"
    job_title: Optional[str] = None
    department: Optional[str] = None
    manager_id: Optional[UUID4] = None
    pay_type: str = "salary"
    pay_rate: DecimalAnnotation
    pay_frequency: str = "biweekly"
    filing_status: str = "single"
    state_code: str = "NY"
    federal_allowances: int = 0
    exempt_from_federal: bool = False
    exempt_from_state: bool = False
    additional_federal_withholding: DecimalAnnotation = Decimal("0")
    health_insurance_deduction: DecimalAnnotation = Decimal("0")
    dental_deduction: DecimalAnnotation = Decimal("0")
    vision_deduction: DecimalAnnotation = Decimal("0")
    retirement_401k_pct: DecimalAnnotation = Decimal("0")
    hsa_deduction: DecimalAnnotation = Decimal("0")
    fsa_deduction: DecimalAnnotation = Decimal("0")
    garnishment_amount: DecimalAnnotation = Decimal("0")
    other_post_tax_deduction: DecimalAnnotation = Decimal("0")
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    class Settings:
        name = "employees"


class OnboardingTask(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    category: Optional[str] = None
    title: str = Field(max_length=255)
    description: Optional[str] = None
    sort_order: int = 0
    is_required: bool = True
    completed: bool = False
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    due_days: int = 7
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "onboarding_tasks"


# ── Payroll ─────────────────────────────────────────────────────
class PayPeriod(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    period_start: date
    period_end: date
    pay_date: date
    frequency: str = "biweekly"
    status: str = "open"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "pay_periods"


class PayRun(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    pay_period_id: UUID4
    status: str = "draft"
    employee_count: int = 0
    total_gross: DecimalAnnotation = Decimal("0")
    total_net: DecimalAnnotation = Decimal("0")
    total_employee_taxes: DecimalAnnotation = Decimal("0")
    total_employer_taxes: DecimalAnnotation = Decimal("0")
    total_deductions: DecimalAnnotation = Decimal("0")
    notes: Optional[str] = None
    created_by: Optional[UUID4] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Settings:
        name = "pay_runs"


class PayRunItem(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    pay_run_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    employee_id: UUID4
    regular_hours: DecimalAnnotation = Decimal("0")
    overtime_hours: DecimalAnnotation = Decimal("0")
    double_time_hours: DecimalAnnotation = Decimal("0")
    regular_pay: DecimalAnnotation = Decimal("0")
    overtime_pay: DecimalAnnotation = Decimal("0")
    bonus_pay: DecimalAnnotation = Decimal("0")
    commission_pay: DecimalAnnotation = Decimal("0")
    reimbursement: DecimalAnnotation = Decimal("0")
    gross_pay: DecimalAnnotation = Decimal("0")
    taxable_gross: DecimalAnnotation = Decimal("0")
    federal_income_tax: DecimalAnnotation = Decimal("0")
    state_income_tax: DecimalAnnotation = Decimal("0")
    local_income_tax: DecimalAnnotation = Decimal("0")
    social_security_tax: DecimalAnnotation = Decimal("0")
    medicare_tax: DecimalAnnotation = Decimal("0")
    additional_medicare_tax: DecimalAnnotation = Decimal("0")
    total_employee_taxes: DecimalAnnotation = Decimal("0")
    employer_social_security: DecimalAnnotation = Decimal("0")
    employer_medicare: DecimalAnnotation = Decimal("0")
    futa_tax: DecimalAnnotation = Decimal("0")
    suta_tax: DecimalAnnotation = Decimal("0")
    total_employer_taxes: DecimalAnnotation = Decimal("0")
    health_insurance: DecimalAnnotation = Decimal("0")
    dental_insurance: DecimalAnnotation = Decimal("0")
    vision_insurance: DecimalAnnotation = Decimal("0")
    retirement_401k: DecimalAnnotation = Decimal("0")
    hsa: DecimalAnnotation = Decimal("0")
    fsa: DecimalAnnotation = Decimal("0")
    total_pretax_deductions: DecimalAnnotation = Decimal("0")
    garnishment: DecimalAnnotation = Decimal("0")
    other_post_tax: DecimalAnnotation = Decimal("0")
    total_posttax_deductions: DecimalAnnotation = Decimal("0")
    net_pay: DecimalAnnotation = Decimal("0")
    ytd_gross: DecimalAnnotation = Decimal("0")
    ytd_net: DecimalAnnotation = Decimal("0")
    ytd_federal_tax: DecimalAnnotation = Decimal("0")
    ytd_state_tax: DecimalAnnotation = Decimal("0")
    ytd_ss_tax: DecimalAnnotation = Decimal("0")
    ytd_medicare_tax: DecimalAnnotation = Decimal("0")
    ytd_401k: DecimalAnnotation = Decimal("0")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "pay_run_items"


class Paystub(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    pay_run_id: Annotated[UUID4, Indexed()]
    pay_run_item_id: UUID4
    employee_id: UUID4
    company_id: Annotated[UUID4, Indexed()]
    pdf_path: Optional[str] = None
    pdf_generated_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "paystubs"


# ── Time & HR ───────────────────────────────────────────────────
class TimeEntry(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    entry_date: date
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    regular_hours: DecimalAnnotation = Decimal("0")
    overtime_hours: DecimalAnnotation = Decimal("0")
    break_minutes: int = 0
    status: str = "pending"
    notes: Optional[str] = None
    approved_by: Optional[UUID4] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "time_entries"


class SalaryBand(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    job_title: str
    department: str
    level: str
    min_salary: DecimalAnnotation
    mid_salary: Optional[DecimalAnnotation] = None
    max_salary: DecimalAnnotation
    currency: str = "USD"
    effective_year: int = Field(default_factory=lambda: datetime.utcnow().year)
    notes: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "salary_bands"


class PtoPolicy(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    name: str
    accrual_rate: DecimalAnnotation = Decimal("0")
    max_accrual: DecimalAnnotation = Decimal("240")
    carryover_limit: DecimalAnnotation = Decimal("80")
    waiting_period_days: int = 90
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "pto_policies"


class PtoBalance(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    policy_id: Optional[UUID4] = None
    available_hours: DecimalAnnotation = Decimal("0")
    used_hours: DecimalAnnotation = Decimal("0")
    pending_hours: DecimalAnnotation = Decimal("0")
    ytd_accrued: DecimalAnnotation = Decimal("0")
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "pto_balances"


class PtoRequest(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    start_date: date
    end_date: date
    hours: DecimalAnnotation
    pto_type: str = "pto"
    status: str = "pending"
    notes: Optional[str] = None
    reviewed_by: Optional[UUID4] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "pto_requests"


# ── Benefits ────────────────────────────────────────────────────
class BenefitPlan(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    plan_type: str
    plan_name: str
    carrier: Optional[str] = None
    plan_code: Optional[str] = None
    employee_cost_per_period: DecimalAnnotation = Decimal("0")
    employer_cost_per_period: DecimalAnnotation = Decimal("0")
    coverage_tier: str = "employee_only"
    details: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    effective_date: Optional[date] = None
    termination_date: Optional[date] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "benefit_plans"


class EnrollmentWindow(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    name: str
    window_type: str = "annual"
    start_date: date
    end_date: date
    effective_date: date
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "enrollment_windows"


class BenefitElection(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    plan_id: UUID4
    enrollment_window_id: Optional[UUID4] = None
    coverage_tier: str = "employee_only"
    employee_contribution: DecimalAnnotation = Decimal("0")
    employer_contribution: DecimalAnnotation = Decimal("0")
    status: str = "active"
    effective_date: Optional[date] = None
    termination_date: Optional[date] = None
    dependents: List[Dict[str, Any]] = Field(default_factory=list)
    elected_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "benefit_elections"


# ── Contractors ──────────────────────────────────────────────────
class Contractor(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    first_name: str
    last_name: str
    business_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    ein_or_ssn_last4: Optional[str] = None
    tin_encrypted: Optional[str] = None
    address_line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    contractor_type: str = "individual"
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "contractors"


class ContractorPayment(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    contractor_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    payment_date: date
    amount: DecimalAnnotation
    description: Optional[str] = None
    payment_method: str = "check"
    reference_number: Optional[str] = None
    tax_year: int
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "contractor_payments"


class EmployeeDocument(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    category: str = Field(default="other", max_length=50)
    original_filename: str = Field(max_length=255)
    stored_filename: str = Field(max_length=255)
    mime_type: Optional[str] = Field(None, max_length=100)
    file_size_bytes: int = 0
    description: Optional[str] = None
    uploaded_by: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "employee_documents"


class BankAccount(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed(unique=True)]
    company_id: Annotated[UUID4, Indexed()]
    bank_name: Optional[str] = Field(None, max_length=100)
    account_type: str = Field(default="checking", max_length=20)
    routing_number_encrypted: Optional[str] = Field(None, max_length=500)
    account_number_encrypted: Optional[str] = Field(None, max_length=500)
    account_last4: Optional[str] = Field(None, max_length=4)
    routing_last4: Optional[str] = Field(None, max_length=4)
    is_verified: bool = False
    is_active: bool = True
    added_at: datetime = Field(default_factory=datetime.utcnow)
    verified_at: Optional[datetime] = None

    class Settings:
        name = "bank_accounts"


# ── Leave & PTO ───────────────────────────────────────────────
class LeaveRecord(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    leave_type: str = Field(max_length=50)
    start_date: date
    expected_return: Optional[date] = None
    actual_return: Optional[date] = None
    is_paid: bool = False
    status: str = Field(default="pending", max_length=20)
    reason: Optional[str] = None
    approved_by: Optional[UUID4] = None
    approved_at: Optional[datetime] = None
    intermittent: bool = False
    documentation_received: bool = False
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "leave_records"


# ── Performance ────────────────────────────────────────────────
class ReviewCycle(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    name: str = Field(max_length=150)
    cycle_type: str = Field(default="annual", max_length=30)
    review_period_start: Optional[date] = None
    review_period_end: Optional[date] = None
    due_date: Optional[date] = None
    status: str = Field(default="draft", max_length=20)
    include_self_review: bool = True
    include_peer_review: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "review_cycles"


class PerformanceReview(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    cycle_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    employee_id: Annotated[UUID4, Indexed()]
    reviewer_id: Optional[UUID4] = None
    review_type: str = Field(default="manager", max_length=20)
    status: str = Field(default="pending", max_length=20)
    overall_rating: Optional[float] = None
    strengths: Optional[str] = None
    areas_for_improvement: Optional[str] = None
    manager_comments: Optional[str] = None
    employee_comments: Optional[str] = None
    ratings: dict = Field(default_factory=dict)
    goals_next_period: Optional[str] = None
    recommended_raise_pct: Optional[float] = None
    recommended_promotion: bool = False
    submitted_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "performance_reviews"


class ReviewGoal(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    review_id: Optional[UUID4] = None
    title: str = Field(max_length=255)
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str = Field(default="active", max_length=20)
    progress_pct: int = 0
    category: str = Field(default="professional", max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    class Settings:
        name = "review_goals"


# ── Expenses & Garnishments ───────────────────────────────────────
class Expense(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    expense_date: date
    category: str = Field(max_length=50)
    description: str = Field(max_length=500)
    amount: float
    currency: str = Field(default="USD", max_length=3)
    vendor: Optional[str] = Field(None, max_length=200)
    receipt_url: Optional[str] = None
    status: str = Field(default="pending", max_length=20)
    is_billable: bool = False
    project_code: Optional[str] = Field(None, max_length=50)
    approved_by: Optional[UUID4] = None
    approved_at: Optional[datetime] = None
    denied_reason: Optional[str] = None
    reimbursed_at: Optional[datetime] = None
    pay_run_id: Optional[UUID4] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "expenses"


class GarnishmentOrder(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    employee_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    garnishment_type: str = Field(max_length=50)
    case_number: Optional[str] = Field(None, max_length=100)
    issuing_agency: Optional[str] = Field(None, max_length=255)
    amount_per_period: float
    amount_type: str = Field(default="fixed", max_length=20)
    percentage: Optional[float] = None
    max_total: Optional[float] = 0
    total_paid: float = 0
    start_date: date
    end_date: Optional[date] = None
    is_active: bool = True
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "garnishment_orders"


# ── ATS (Hiring) ────────────────────────────────────────────────
class JobPosting(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    title: str = Field(max_length=200)
    department: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    work_mode: str = Field(default="onsite", max_length=20)
    job_type: str = Field(default="full_time", max_length=20)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    benefits_summary: Optional[str] = None
    status: str = Field(default="draft", max_length=20)
    target_hire_date: Optional[date] = None
    headcount: int = 1
    filled_count: int = 0
    hiring_manager_id: Optional[UUID4] = None
    posted_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "job_postings"


class Candidate(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    job_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    email: str = Field(max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    resume_url: Optional[str] = Field(None, max_length=500)
    stage: str = Field(default="applied", max_length=30)
    rating: Optional[int] = None
    source: str = Field(default="direct", max_length=50)
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    rejected_reason: Optional[str] = Field(None, max_length=200)
    offer_amount: Optional[int] = None
    offer_date: Optional[date] = None
    hired_date: Optional[date] = None
    employee_id: Optional[UUID4] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "candidates"


class HiringNote(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    candidate_id: Annotated[UUID4, Indexed()]
    company_id: Annotated[UUID4, Indexed()]
    author_id: Optional[UUID4] = None
    author_name: Optional[str] = Field(None, max_length=200)
    note_type: str = Field(default="general", max_length=30)
    content: str
    rating: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "hiring_notes"


# ── System / Infrastructure ───────────────────────────────────────
class ApiKey(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    name: str = Field(max_length=100)
    key_hash: Annotated[str, Indexed(unique=True)]
    key_prefix: str = Field(max_length=20)
    environment: str = Field(default="live", max_length=10)
    scopes: str = "*"
    is_active: bool = True
    last_used: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    class Settings:
        name = "api_keys"


# class Webhook(Document):
#     id: UUID4 = Field(default_factory=uuid.uuid4)
#     company_id: Annotated[UUID4, Indexed()]
#     url: str
#     secret: str = Field(max_length=64)
#     events: str = "*"
#     is_active: bool = True
#     created_at: datetime = Field(default_factory=datetime.utcnow)
#     last_triggered: Optional[datetime] = None
#     failure_count: str = Field(default="0", max_length=10)
#
#     class Settings:
#         name = "webhooks"
#
#
# class WebhookDeliveryLog(Document):
#     id: UUID4 = Field(default_factory=uuid.uuid4)
#     webhook_id: Annotated[UUID4, Indexed()]
#     event: Optional[str] = Field(None, max_length=100)
#     payload_summary: Optional[str] = None
#     status_code: Optional[str] = Field(None, max_length=10)
#     success: bool = False
#     attempt: str = Field(default="1", max_length=5)
#     created_at: datetime = Field(default_factory=datetime.utcnow)
#
#     class Settings:
#         name = "webhook_deliveries"


class EmployeeUserLink(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    user_id: Annotated[UUID4, Indexed(unique=True)]
    employee_id: Annotated[UUID4, Indexed(unique=True)]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "employee_user_links"


class ScheduleConfig(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed(unique=True)]
    frequency: str = Field(default="biweekly", max_length=20)
    next_period_start: Optional[date] = None
    next_run_date: Optional[date] = None
    auto_approve: bool = False
    notify_email: Optional[str] = Field(None, max_length=255)
    is_active: bool = False
    last_run: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "payroll_schedules"


class CustomFieldSchema(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    entity_type: str = Field(max_length=30)
    field_name: str = Field(max_length=100)
    display_name: str = Field(max_length=200)
    field_type: str = Field(max_length=30)
    options: List[Any] = Field(default_factory=list)
    required: bool = False
    description: Optional[str] = None
    sort_order: str = Field(default="0", max_length=5)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "custom_field_schemas"


class CustomFieldValue(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    schema_id: Annotated[UUID4, Indexed()]
    entity_type: str = Field(max_length=30)
    entity_id: str = Field(max_length=100)
    value_text: Optional[str] = None
    value_json: Optional[Any] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "custom_field_values"


class PayrollAdjustment(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    employee_id: Annotated[UUID4, Indexed()]
    adjustment_type: str = Field(max_length=50)
    amount: float
    is_taxable: bool = True
    description: Optional[str] = None
    effective_date: date
    status: str = Field(default="pending", max_length=20)
    pay_run_id: Optional[UUID4] = None
    approved_by: Optional[UUID4] = None
    created_by: Optional[UUID4] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    applied_at: Optional[datetime] = None

    class Settings:
        name = "payroll_adjustments"


# ── Audit & Notifications ───────────────────────────────────────
class Notification(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    user_id: Optional[UUID4] = None
    type: str
    title: str
    body: Optional[str] = None
    action_url: Optional[str] = None
    severity: str = "info"
    is_read: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    read_at: Optional[datetime] = None

    class Settings:
        name = "notifications"


class AuditLog(Document):
    id: UUID4 = Field(default_factory=uuid.uuid4)
    company_id: Annotated[UUID4, Indexed()]
    user_id: Optional[UUID4] = None
    user_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "audit_logs"
