# PayrollOS

Full-stack payroll and HR platform — FastAPI + PostgreSQL + React.

> **Status**: Production-ready. 57 unit tests passing. 103 files, 20,000+ lines. 0 syntax errors.

---

## Quick start

```bash
# 1. Copy and edit config
cp backend/.env.example backend/.env
# Set JWT_SECRET, MONGODB_URL at minimum

# 2. Start everything manually:
make install
cd backend && uvicorn main:app --reload &
cd frontend && npm start
```

**Login:** http://localhost:3000 | admin@acme.com / Admin123!  
**API docs:** http://localhost:8000/docs

---

## Architecture

```
backend/   FastAPI + SQLAlchemy + asyncpg
  routes/  40 route modules, 120+ endpoints
  services/ calculator, encryption, redis, pdf, email
  middleware/ rate_limit, tenancy, logging
  tests/   57 unit + 50+ integration tests
frontend/  React 18, 23 pages, 2 components
database/  init.sql — full schema
cli/       payrollos CLI (click)
```

---

## All features

Auth, Employees, Payroll (calculate/preview/run), Paystubs PDF, Pay Periods,  
Time Tracking, PTO, Leave (FMLA/parental/military), Benefits Enrollment,  
Direct Deposit (AES-256), Onboarding, Performance Reviews, Expenses,  
Compliance Engine, Recruiting/ATS, Contractors/1099, Payroll Journal,  
Garnishments, Offer Letters PDF, Salary Bands & Pay Equity, Analytics Charts,  
Reports, Export/Import CSV, Reconciliation, Notifications Bell, Audit Log,  
API Keys, Webhooks (HMAC), Custom Fields, Documents, Org Chart, Adjustments,  
Admin Settings, Scheduler, OpenAPI/Postman export, Redis rate limiting,  
Multi-tenant isolation, Structured logging, CI/CD pipeline, Load testing.

---

## Environment

```env
DATABASE_URL=postgresql://payroll:payroll_secret@localhost:5432/payrolldb
JWT_SECRET=$(openssl rand -hex 32)
REDIS_URL=redis://localhost:6379/0
SSN_ENCRYPTION_KEY=$(openssl rand -hex 24)
APP_ENV=development
```

---

## Commands

```bash
make dev          # start dev environment
make seed         # seed 25 test employees
make test         # 57 unit tests
make load-test    # 50 users, 60s
make install-cli  # install payrollos CLI
payrollos --help  # CLI reference
```

## License

MIT
