from fastapi import FastAPI
from startup import lifespan
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from middleware.logging_mw import RequestLogMiddleware
from utils.logging_config import setup_logging
setup_logging()

from routes import (auth, employees, payroll, paystubs, time, company, reports, pay_periods,
    password_reset, export, import_routes, audit, users, api_keys, pto, onboarding,
    offer_letters, w2, journal, garnishments, health as health_routes, scheduler, documents,
    self_service, benefits, direct_deposit, salary_bands, contractors, leave, openapi_export,
    performance, expenses, compliance, notifications, org_chart, adjustments,
    ats, custom_fields, reconciliation)
import os

app = FastAPI(
    lifespan=lifespan,
    title="PayrollOS API",
    description="Complete payroll system API - built in 3 days",
    version="1.0.0",
)

from middleware.tenancy import MultiTenantMiddleware
app.add_middleware(MultiTenantMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://payroll.qbxpress.com", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(payroll.router)
app.include_router(paystubs.router)
app.include_router(time.router)
app.include_router(company.router)
app.include_router(reports.router)
app.include_router(pay_periods.router)
app.include_router(password_reset.router)
app.include_router(export.router)
app.include_router(import_routes.router)
app.include_router(audit.router)
app.include_router(users.router)
app.include_router(api_keys.router)
app.include_router(pto.router)
app.include_router(onboarding.router)
app.include_router(offer_letters.router)
app.include_router(w2.router)
app.include_router(journal.router)
app.include_router(garnishments.router)
app.include_router(health_routes.router)
app.include_router(scheduler.router)
app.include_router(documents.router)
app.include_router(self_service.router)
app.include_router(benefits.router)
app.include_router(direct_deposit.router)
app.include_router(salary_bands.router)
app.include_router(contractors.router)
app.include_router(leave.router)
app.include_router(openapi_export.router)
app.include_router(performance.router)
app.include_router(expenses.router)
app.include_router(compliance.router)
app.include_router(notifications.router)
app.include_router(org_chart.router)
app.include_router(adjustments.router)
app.include_router(ats.router)
app.include_router(custom_fields.router)
app.include_router(reconciliation.router)

os.makedirs(settings.PAYSTUB_DIR, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "PayrollOS API"}


@app.get("/")
async def root():
    return {
        "service": "PayrollOS API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "auth": "/auth/login | /auth/register",
            "employees": "/employees",
            "payroll_preview": "/payroll/preview",
            "payroll_run": "/payroll/run",
            "payroll_history": "/payroll/history",
            "payroll_calculator": "/payroll/calculate",
            "paystubs": "/paystubs/{id}",
            "paystub_pdf": "/paystubs/{id}/download",
            "time_entries": "/time",
            "company": "/company",
            "reports_ytd": "/reports/ytd-summary",
            "reports_dept": "/reports/by-department",
            "reports_employee": "/reports/employee-ytd",
            "reports_tax": "/reports/tax-liability",
            "pay_periods": "/pay-periods",
        }
    }
