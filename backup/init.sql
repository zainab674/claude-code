
-- ============================================================
-- ATS — JOB POSTINGS & CANDIDATES
-- ============================================================
CREATE TABLE IF NOT EXISTS job_postings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    department VARCHAR(100),
    location VARCHAR(200),
    work_mode VARCHAR(20) DEFAULT 'onsite',
    job_type VARCHAR(20) DEFAULT 'full_time',
    salary_min INT,
    salary_max INT,
    description TEXT,
    requirements TEXT,
    benefits_summary TEXT,
    status VARCHAR(20) DEFAULT 'draft',
    target_hire_date DATE,
    headcount INT DEFAULT 1,
    filled_count INT DEFAULT 0,
    hiring_manager_id UUID REFERENCES employees(id),
    posted_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON job_postings(company_id, status);

CREATE TABLE IF NOT EXISTS candidates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES job_postings(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(30),
    linkedin_url VARCHAR(500),
    resume_url VARCHAR(500),
    stage VARCHAR(30) DEFAULT 'applied',
    rating INT,
    source VARCHAR(50) DEFAULT 'direct',
    notes TEXT,
    tags JSONB DEFAULT '[]',
    rejected_reason VARCHAR(200),
    offer_amount INT,
    offer_date DATE,
    hired_date DATE,
    employee_id UUID REFERENCES employees(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_candidates_job ON candidates(job_id, stage);

CREATE TABLE IF NOT EXISTS hiring_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id),
    author_name VARCHAR(200),
    note_type VARCHAR(30) DEFAULT 'general',
    content TEXT NOT NULL,
    rating INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- CUSTOM FIELDS
-- ============================================================
CREATE TABLE IF NOT EXISTS custom_field_schemas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    entity_type VARCHAR(30) NOT NULL,
    field_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    field_type VARCHAR(30) NOT NULL,
    options JSONB DEFAULT '[]',
    required BOOLEAN DEFAULT FALSE,
    description TEXT,
    sort_order VARCHAR(5) DEFAULT '0',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, entity_type, field_name)
);

CREATE TABLE IF NOT EXISTS custom_field_values (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    schema_id UUID REFERENCES custom_field_schemas(id) ON DELETE CASCADE,
    entity_type VARCHAR(30) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    value_text TEXT,
    value_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cfv_entity ON custom_field_values(entity_type, entity_id);


-- ============================================================
-- PAYROLL ADJUSTMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS payroll_adjustments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    adjustment_type VARCHAR(50) NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    is_taxable BOOLEAN DEFAULT TRUE,
    description TEXT,
    effective_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    pay_run_id UUID REFERENCES pay_runs(id),
    approved_by UUID REFERENCES users(id),
    created_by UUID REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_adjustments_employee ON payroll_adjustments(employee_id, status);


-- ============================================================
-- PERFORMANCE REVIEWS
-- ============================================================
CREATE TABLE IF NOT EXISTS review_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    cycle_type VARCHAR(30) DEFAULT 'annual',
    review_period_start DATE,
    review_period_end DATE,
    due_date DATE,
    status VARCHAR(20) DEFAULT 'draft',
    include_self_review BOOLEAN DEFAULT TRUE,
    include_peer_review BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS performance_reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id UUID REFERENCES review_cycles(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    reviewer_id UUID REFERENCES employees(id),
    review_type VARCHAR(20) DEFAULT 'manager',
    status VARCHAR(20) DEFAULT 'pending',
    overall_rating NUMERIC(3,1),
    strengths TEXT,
    areas_for_improvement TEXT,
    manager_comments TEXT,
    employee_comments TEXT,
    ratings JSONB DEFAULT '{}',
    goals_next_period TEXT,
    recommended_raise_pct NUMERIC(5,2),
    recommended_promotion BOOLEAN DEFAULT FALSE,
    submitted_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_reviews_employee ON performance_reviews(employee_id, status);

CREATE TABLE IF NOT EXISTS review_goals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    review_id UUID REFERENCES performance_reviews(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    due_date DATE,
    status VARCHAR(20) DEFAULT 'active',
    progress_pct INT DEFAULT 0,
    category VARCHAR(50) DEFAULT 'professional',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ============================================================
-- EXPENSES
-- ============================================================
CREATE TABLE IF NOT EXISTS expenses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    expense_date DATE NOT NULL,
    category VARCHAR(50) NOT NULL,
    description VARCHAR(500) NOT NULL,
    amount NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    vendor VARCHAR(200),
    receipt_url TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    is_billable BOOLEAN DEFAULT FALSE,
    project_code VARCHAR(50),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    denied_reason TEXT,
    reimbursed_at TIMESTAMPTZ,
    pay_run_id UUID REFERENCES pay_runs(id),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_expenses_employee ON expenses(employee_id, status);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);

-- ============================================================
-- NOTIFICATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    action_url VARCHAR(500),
    severity VARCHAR(20) DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    read_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(company_id, user_id, is_read);


-- ============================================================
-- SALARY BANDS
-- ============================================================
CREATE TABLE IF NOT EXISTS salary_bands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    job_title VARCHAR(150),
    department VARCHAR(100),
    level VARCHAR(50),
    min_salary NUMERIC(12,2) NOT NULL,
    mid_salary NUMERIC(12,2),
    max_salary NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    effective_year INT,
    notes VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_salary_bands_company ON salary_bands(company_id);

-- ============================================================
-- CONTRACTORS & PAYMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS contractors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    business_name VARCHAR(200),
    email VARCHAR(255),
    phone VARCHAR(20),
    ein_or_ssn_last4 VARCHAR(4),
    tin_encrypted VARCHAR(500),
    address_line1 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip VARCHAR(10),
    contractor_type VARCHAR(30) DEFAULT 'individual',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contractor_payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    contractor_id UUID REFERENCES contractors(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    payment_date DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    description TEXT,
    payment_method VARCHAR(30) DEFAULT 'check',
    reference_number VARCHAR(100),
    tax_year INT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_contractor_payments ON contractor_payments(contractor_id, tax_year);

-- ============================================================
-- LEAVE MANAGEMENT
-- ============================================================
CREATE TABLE IF NOT EXISTS leave_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    leave_type VARCHAR(50) NOT NULL,
    start_date DATE NOT NULL,
    expected_return DATE,
    actual_return DATE,
    is_paid BOOLEAN DEFAULT FALSE,
    status VARCHAR(20) DEFAULT 'pending',
    reason TEXT,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    intermittent BOOLEAN DEFAULT FALSE,
    documentation_received BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_leave_employee ON leave_records(employee_id, status);
CREATE INDEX IF NOT EXISTS idx_leave_dates ON leave_records(start_date, expected_return);

-- ============================================================
-- BANK ACCOUNTS (direct deposit)
-- ============================================================
CREATE TABLE IF NOT EXISTS bank_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID UNIQUE REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    bank_name VARCHAR(100),
    account_type VARCHAR(20) DEFAULT 'checking',
    routing_number_encrypted VARCHAR(500),
    account_number_encrypted VARCHAR(500),
    account_last4 VARCHAR(4),
    routing_last4 VARCHAR(4),
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    verified_at TIMESTAMPTZ
);

-- ============================================================
-- BENEFIT PLANS & ELECTIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS benefit_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    plan_type VARCHAR(30) NOT NULL,
    plan_name VARCHAR(100) NOT NULL,
    carrier VARCHAR(100),
    plan_code VARCHAR(50),
    employee_cost_per_period NUMERIC(10,2) DEFAULT 0,
    employer_cost_per_period NUMERIC(10,2) DEFAULT 0,
    coverage_tier VARCHAR(30) DEFAULT 'employee_only',
    details JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE,
    termination_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS enrollment_windows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    window_type VARCHAR(30) DEFAULT 'annual',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    effective_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS benefit_elections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    plan_id UUID REFERENCES benefit_plans(id),
    enrollment_window_id UUID REFERENCES enrollment_windows(id),
    coverage_tier VARCHAR(30) DEFAULT 'employee_only',
    employee_contribution NUMERIC(10,2) DEFAULT 0,
    employer_contribution NUMERIC(10,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    effective_date DATE,
    termination_date DATE,
    dependents JSONB DEFAULT '[]',
    elected_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_elections_employee ON benefit_elections(employee_id, status);

-- ============================================================
-- SELF-SERVICE EMPLOYEE-USER LINKS
-- ============================================================
CREATE TABLE IF NOT EXISTS employee_user_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    employee_id UUID UNIQUE REFERENCES employees(id) ON DELETE CASCADE,
    created_at VARCHAR(50)
);

-- ============================================================
-- PAYROLL SYSTEM - COMPLETE DATABASE SCHEMA
-- Day 1-3 Accelerated Build
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- COMPANIES
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    ein VARCHAR(20),                      -- Employer Identification Number
    address_line1 VARCHAR(255),
    address_line2 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip VARCHAR(10),
    phone VARCHAR(20),
    email VARCHAR(255),
    pay_frequency VARCHAR(20) DEFAULT 'biweekly'  -- weekly, biweekly, semimonthly, monthly
        CHECK (pay_frequency IN ('weekly','biweekly','semimonthly','monthly')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- USERS (auth)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) DEFAULT 'admin' CHECK (role IN ('admin','manager','viewer')),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- EMPLOYEES
-- ============================================================
CREATE TABLE IF NOT EXISTS employees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_number VARCHAR(50) UNIQUE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(20),
    ssn_encrypted TEXT,                   -- AES-256 encrypted
    date_of_birth DATE,
    hire_date DATE NOT NULL,
    termination_date DATE,
    status VARCHAR(20) DEFAULT 'active'
        CHECK (status IN ('active','inactive','terminated')),

    -- Pay info
    pay_type VARCHAR(20) NOT NULL CHECK (pay_type IN ('salary','hourly','contract')),
    pay_rate NUMERIC(12,4) NOT NULL,      -- annual salary OR hourly rate
    pay_frequency VARCHAR(20) DEFAULT 'biweekly',
    department VARCHAR(100),
    job_title VARCHAR(150),

    -- Tax withholding
    filing_status VARCHAR(20) DEFAULT 'single'
        CHECK (filing_status IN ('single','married','head_of_household')),
    federal_allowances INT DEFAULT 0,
    additional_federal_withholding NUMERIC(10,2) DEFAULT 0,
    state_code VARCHAR(2) DEFAULT 'NY',
    exempt_from_federal BOOLEAN DEFAULT FALSE,
    exempt_from_state BOOLEAN DEFAULT FALSE,

    -- Benefits
    health_insurance_deduction NUMERIC(10,2) DEFAULT 0,
    dental_deduction NUMERIC(10,2) DEFAULT 0,
    vision_deduction NUMERIC(10,2) DEFAULT 0,
    retirement_401k_pct NUMERIC(5,4) DEFAULT 0, -- e.g. 0.05 = 5%
    hsa_deduction NUMERIC(10,2) DEFAULT 0,

    -- Garnishments
    garnishment_amount NUMERIC(10,2) DEFAULT 0,
    garnishment_type VARCHAR(50),

    -- Address
    address_line1 VARCHAR(255),
    city VARCHAR(100),
    state VARCHAR(2),
    zip VARCHAR(10),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PAY PERIODS
-- ============================================================
CREATE TABLE IF NOT EXISTS pay_periods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    pay_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'open'
        CHECK (status IN ('open','processing','completed','cancelled')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (company_id, period_start, period_end)
);

-- ============================================================
-- PAY RUNS
-- ============================================================
CREATE TABLE IF NOT EXISTS pay_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    pay_period_id UUID NOT NULL REFERENCES pay_periods(id),
    run_number SERIAL,
    status VARCHAR(20) DEFAULT 'draft'
        CHECK (status IN ('draft','preview','approved','processing','completed','failed')),

    -- Totals
    total_gross NUMERIC(14,2) DEFAULT 0,
    total_employee_taxes NUMERIC(14,2) DEFAULT 0,
    total_employer_taxes NUMERIC(14,2) DEFAULT 0,
    total_deductions NUMERIC(14,2) DEFAULT 0,
    total_net NUMERIC(14,2) DEFAULT 0,
    employee_count INT DEFAULT 0,

    notes TEXT,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ============================================================
-- PAY RUN ITEMS (one per employee per run)
-- ============================================================
CREATE TABLE IF NOT EXISTS pay_run_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pay_run_id UUID NOT NULL REFERENCES pay_runs(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id),
    company_id UUID NOT NULL REFERENCES companies(id),

    -- Hours (for hourly employees)
    regular_hours NUMERIC(8,2) DEFAULT 0,
    overtime_hours NUMERIC(8,2) DEFAULT 0,
    double_time_hours NUMERIC(8,2) DEFAULT 0,
    pto_hours NUMERIC(8,2) DEFAULT 0,
    sick_hours NUMERIC(8,2) DEFAULT 0,
    holiday_hours NUMERIC(8,2) DEFAULT 0,

    -- Earnings
    regular_pay NUMERIC(12,2) DEFAULT 0,
    overtime_pay NUMERIC(12,2) DEFAULT 0,
    double_time_pay NUMERIC(12,2) DEFAULT 0,
    bonus_pay NUMERIC(12,2) DEFAULT 0,
    commission_pay NUMERIC(12,2) DEFAULT 0,
    reimbursement NUMERIC(12,2) DEFAULT 0,
    gross_pay NUMERIC(12,2) DEFAULT 0,

    -- Employee taxes
    federal_income_tax NUMERIC(10,2) DEFAULT 0,
    state_income_tax NUMERIC(10,2) DEFAULT 0,
    local_income_tax NUMERIC(10,2) DEFAULT 0,
    social_security_tax NUMERIC(10,2) DEFAULT 0,  -- 6.2%
    medicare_tax NUMERIC(10,2) DEFAULT 0,          -- 1.45%
    additional_medicare_tax NUMERIC(10,2) DEFAULT 0, -- 0.9% over $200k
    sdi_tax NUMERIC(10,2) DEFAULT 0,               -- State Disability
    total_employee_taxes NUMERIC(10,2) DEFAULT 0,

    -- Employer taxes
    employer_social_security NUMERIC(10,2) DEFAULT 0,  -- 6.2%
    employer_medicare NUMERIC(10,2) DEFAULT 0,           -- 1.45%
    futa_tax NUMERIC(10,2) DEFAULT 0,                    -- 0.6% up to $7k
    suta_tax NUMERIC(10,2) DEFAULT 0,                    -- varies by state
    total_employer_taxes NUMERIC(10,2) DEFAULT 0,

    -- Pre-tax deductions
    health_insurance NUMERIC(10,2) DEFAULT 0,
    dental_insurance NUMERIC(10,2) DEFAULT 0,
    vision_insurance NUMERIC(10,2) DEFAULT 0,
    retirement_401k NUMERIC(10,2) DEFAULT 0,
    hsa NUMERIC(10,2) DEFAULT 0,
    total_pretax_deductions NUMERIC(10,2) DEFAULT 0,

    -- Post-tax deductions
    garnishment NUMERIC(10,2) DEFAULT 0,
    total_posttax_deductions NUMERIC(10,2) DEFAULT 0,

    net_pay NUMERIC(12,2) DEFAULT 0,

    -- YTD accumulators (snapshot at time of run)
    ytd_gross NUMERIC(14,2) DEFAULT 0,
    ytd_federal_tax NUMERIC(14,2) DEFAULT 0,
    ytd_social_security NUMERIC(14,2) DEFAULT 0,
    ytd_medicare NUMERIC(14,2) DEFAULT 0,
    ytd_net NUMERIC(14,2) DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PAYSTUBS
-- ============================================================
CREATE TABLE IF NOT EXISTS paystubs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pay_run_item_id UUID NOT NULL REFERENCES pay_run_items(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id),
    company_id UUID NOT NULL REFERENCES companies(id),
    pay_run_id UUID NOT NULL REFERENCES pay_runs(id),
    pdf_path TEXT,
    pdf_generated_at TIMESTAMPTZ,
    viewed_at TIMESTAMPTZ,
    downloaded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- TIME ENTRIES (for hourly employees)
-- ============================================================
CREATE TABLE IF NOT EXISTS time_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id),
    pay_period_id UUID REFERENCES pay_periods(id),
    entry_date DATE NOT NULL,
    clock_in TIMESTAMPTZ,
    clock_out TIMESTAMPTZ,
    regular_hours NUMERIC(6,2) DEFAULT 0,
    overtime_hours NUMERIC(6,2) DEFAULT 0,
    entry_type VARCHAR(20) DEFAULT 'work'
        CHECK (entry_type IN ('work','pto','sick','holiday','unpaid')),
    notes TEXT,
    approved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_employees_company ON employees(company_id);
CREATE INDEX idx_employees_status ON employees(status);
CREATE INDEX idx_pay_runs_company ON pay_runs(company_id);
CREATE INDEX idx_pay_runs_period ON pay_runs(pay_period_id);
CREATE INDEX idx_pay_run_items_run ON pay_run_items(pay_run_id);
CREATE INDEX idx_pay_run_items_employee ON pay_run_items(employee_id);
CREATE INDEX idx_paystubs_employee ON paystubs(employee_id);
CREATE INDEX idx_time_entries_employee ON time_entries(employee_id);

-- ============================================================
-- TRIGGERS - updated_at auto-update
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_companies_updated BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_employees_updated BEFORE UPDATE ON employees
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();






-- ============================================================
-- SCHEDULER
-- ============================================================
CREATE TABLE IF NOT EXISTS payroll_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
    frequency VARCHAR(20) DEFAULT 'biweekly',
    next_period_start DATE,
    next_run_date DATE,
    auto_approve BOOLEAN DEFAULT FALSE,
    notify_email VARCHAR(255),
    is_active BOOLEAN DEFAULT FALSE,
    last_run TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- EMPLOYEE DOCUMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS employee_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    category VARCHAR(50) DEFAULT 'other',
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100),
    file_size_bytes INT DEFAULT 0,
    description TEXT,
    uploaded_by VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_emp_docs ON employee_documents(employee_id, is_active);

-- ============================================================
-- GARNISHMENT ORDERS
-- ============================================================
CREATE TABLE IF NOT EXISTS garnishment_orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    garnishment_type VARCHAR(50) NOT NULL,
    case_number VARCHAR(100),
    issuing_agency VARCHAR(255),
    amount_per_period NUMERIC(10,2) NOT NULL,
    amount_type VARCHAR(20) DEFAULT 'fixed',
    percentage NUMERIC(5,4),
    max_total NUMERIC(12,2),
    total_paid NUMERIC(12,2) DEFAULT 0,
    start_date DATE NOT NULL,
    end_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_garnishment_emp ON garnishment_orders(employee_id, is_active);

-- ============================================================
-- PTO TRACKING
-- ============================================================
CREATE TABLE IF NOT EXISTS pto_policies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    accrual_rate NUMERIC(8,4) DEFAULT 3.08,
    max_accrual NUMERIC(8,2) DEFAULT 240,
    carryover_limit NUMERIC(8,2) DEFAULT 80,
    waiting_period_days INT DEFAULT 90,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pto_balances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID UNIQUE REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    policy_id UUID REFERENCES pto_policies(id),
    available_hours NUMERIC(8,2) DEFAULT 0,
    used_hours NUMERIC(8,2) DEFAULT 0,
    pending_hours NUMERIC(8,2) DEFAULT 0,
    ytd_accrued NUMERIC(8,2) DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pto_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    hours NUMERIC(8,2) NOT NULL,
    pto_type VARCHAR(30) DEFAULT 'pto',
    status VARCHAR(20) DEFAULT 'pending',
    notes TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ONBOARDING
-- ============================================================
CREATE TABLE IF NOT EXISTS onboarding_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employee_id UUID REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    category VARCHAR(100),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    sort_order INT DEFAULT 0,
    is_required BOOLEAN DEFAULT TRUE,
    completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    completed_by VARCHAR(255),
    due_days INT DEFAULT 7,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- API KEYS
-- ============================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(20) NOT NULL,
    environment VARCHAR(10) DEFAULT 'live',
    scopes TEXT DEFAULT '*',
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_company ON api_keys(company_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_pto_balance_emp ON pto_balances(employee_id);
CREATE INDEX IF NOT EXISTS idx_pto_req_emp ON pto_requests(employee_id, status);
CREATE INDEX IF NOT EXISTS idx_onboarding_emp ON onboarding_tasks(employee_id);

-- Default PTO policy for seed company
INSERT INTO pto_policies (company_id, name, accrual_rate, max_accrual, carryover_limit, waiting_period_days)
VALUES ('00000000-0000-0000-0000-000000000001', 'Standard PTO', 3.08, 240, 80, 90)
ON CONFLICT DO NOTHING;

-- ============================================================
-- WEBHOOKS
-- ============================================================
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    secret VARCHAR(64) NOT NULL,
    events TEXT DEFAULT '*',
    is_active BOOLEAN DEFAULT TRUE,
    last_triggered TIMESTAMPTZ,
    failure_count VARCHAR(10) DEFAULT '0',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    webhook_id UUID REFERENCES webhooks(id) ON DELETE CASCADE,
    event VARCHAR(100),
    payload_summary TEXT,
    status_code VARCHAR(10),
    success BOOLEAN DEFAULT FALSE,
    attempt VARCHAR(5) DEFAULT '1',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_company ON webhooks(company_id);
CREATE INDEX IF NOT EXISTS idx_wh_deliveries ON webhook_deliveries(webhook_id, created_at DESC);

-- ============================================================
-- AUDIT LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_email VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(100),
    details JSONB DEFAULT '{}',
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_company ON audit_logs(company_id);
CREATE INDEX idx_audit_action ON audit_logs(action);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);

-- ============================================================
-- SEED DATA
-- ============================================================
INSERT INTO companies (id, name, ein, address_line1, city, state, zip, pay_frequency)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Acme Corp',
    '12-3456789',
    '100 Main Street',
    'New York',
    'NY',
    '10001',
    'biweekly'
);

INSERT INTO users (company_id, email, password_hash, role, first_name, last_name)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'admin@acme.com',
    crypt('Admin123!', gen_salt('bf')),
    'admin',
    'Admin',
    'User'
);

INSERT INTO employees (company_id, first_name, last_name, email, hire_date, pay_type, pay_rate, department, job_title, filing_status, state_code, health_insurance_deduction, retirement_401k_pct)
VALUES
    ('00000000-0000-0000-0000-000000000001','Sarah','Chen','sarah@acme.com','2022-01-15','salary',150000,'Engineering','Lead Engineer','single','NY',300,0.06),
    ('00000000-0000-0000-0000-000000000001','Marcus','Webb','marcus@acme.com','2022-03-01','salary',130000,'Engineering','Senior Engineer','married','NY',300,0.05),
    ('00000000-0000-0000-0000-000000000001','Priya','Nair','priya@acme.com','2023-06-01','salary',120000,'Product','Product Manager','single','NY',150,0.04),
    ('00000000-0000-0000-0000-000000000001','James','Liu','james@acme.com','2023-09-15','salary',100000,'Design','Lead Designer','single','NY',150,0.03),
    ('00000000-0000-0000-0000-000000000001','Dana','Park','dana@acme.com','2024-01-08','hourly',45.00,'QA','QA Engineer','single','NY',0,0.02);
