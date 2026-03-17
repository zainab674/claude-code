"""
Integration tests — test all API endpoints against a live server.
Requires a running backend with test DB.

Run:
    pytest tests/test_integration.py -v --tb=short

Set env vars:
    PAYROLLOS_TEST_URL=http://localhost:8000
    PAYROLLOS_TEST_EMAIL=admin@acme.com
    PAYROLLOS_TEST_PASSWORD=Admin123!
"""
import os
import pytest
import httpx

BASE = os.getenv("PAYROLLOS_TEST_URL", "http://localhost:8000")
EMAIL = os.getenv("PAYROLLOS_TEST_EMAIL", "admin@acme.com")
PASSWORD = os.getenv("PAYROLLOS_TEST_PASSWORD", "Admin123!")


@pytest.fixture(scope="session")
def auth_headers():
    """Authenticate once per session and return headers."""
    r = httpx.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Cannot connect to {BASE} or login failed: {r.status_code}")
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def client(auth_headers):
    return httpx.Client(base_url=BASE, headers=auth_headers, timeout=30)


# ── Health ─────────────────────────────────────────────────────
class TestHealth:
    def test_basic_health(self):
        r = httpx.get(f"{BASE}/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_detailed_health(self, client):
        r = client.get("/health/detailed")
        assert r.status_code == 200
        data = r.json()
        assert "checks" in data
        assert "database" in data["checks"]


# ── Auth ───────────────────────────────────────────────────────
class TestAuth:
    def test_login_success(self):
        r = httpx.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == EMAIL

    def test_login_wrong_password(self):
        r = httpx.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": "wrongpass"})
        assert r.status_code == 401

    def test_protected_endpoint_no_token(self):
        r = httpx.get(f"{BASE}/employees")
        assert r.status_code == 403


# ── Employees ──────────────────────────────────────────────────
class TestEmployees:
    def test_list_employees(self, client):
        r = client.get("/employees")
        assert r.status_code == 200
        data = r.json()
        assert "employees" in data
        assert "total" in data

    def test_list_employees_filter_status(self, client):
        r = client.get("/employees?status=active")
        assert r.status_code == 200
        for emp in r.json()["employees"]:
            assert emp["status"] == "active"

    def test_create_employee(self, client):
        payload = {
            "first_name": "Test",
            "last_name": "Integration",
            "email": "test.integration@example.com",
            "hire_date": "2026-01-01",
            "pay_type": "salary",
            "pay_rate": 60000,
            "department": "Testing",
            "job_title": "Test Engineer",
            "state_code": "NY",
            "filing_status": "single",
        }
        r = client.post("/employees", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["first_name"] == "Test"
        assert data["pay_rate"] == 60000.0
        return data["id"]

    def test_get_employee(self, client):
        # Get any active employee
        emps = client.get("/employees?status=active").json()["employees"]
        if emps:
            emp_id = emps[0]["id"]
            r = client.get(f"/employees/{emp_id}")
            assert r.status_code == 200
            assert r.json()["id"] == emp_id

    def test_update_employee(self, client):
        emps = client.get("/employees?status=active").json()["employees"]
        if emps:
            emp_id = emps[0]["id"]
            r = client.put(f"/employees/{emp_id}", json={"department": "Updated Dept"})
            assert r.status_code == 200
            assert r.json()["department"] == "Updated Dept"

    def test_search_employees(self, client):
        r = client.get("/employees?search=Test")
        assert r.status_code == 200


# ── Company ────────────────────────────────────────────────────
class TestCompany:
    def test_get_company(self, client):
        r = client.get("/company")
        assert r.status_code == 200
        data = r.json()
        assert "name" in data

    def test_update_company(self, client):
        r = client.put("/company", json={"phone": "555-0100"})
        assert r.status_code == 200


# ── Payroll Calculator ─────────────────────────────────────────
class TestCalculator:
    def test_salary_calculation(self, client):
        r = client.post("/payroll/calculate", json={
            "pay_type": "salary",
            "annual_salary": 75000,
            "pay_frequency": "biweekly",
            "filing_status": "single",
            "state_code": "NY",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["gross_pay"] > 0
        assert data["net_pay"] < data["gross_pay"]
        assert data["federal_income_tax"] > 0
        assert data["state_income_tax"] > 0

    def test_hourly_calculation(self, client):
        r = client.post("/payroll/calculate", json={
            "pay_type": "hourly",
            "hourly_rate": 25.0,
            "pay_frequency": "biweekly",
            "filing_status": "single",
            "state_code": "TX",
            "regular_hours": 80,
            "overtime_hours": 5,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["gross_pay"] == pytest.approx(25 * 80 + 25 * 1.5 * 5, abs=0.01)
        assert data["state_income_tax"] == 0.0   # TX = no state tax

    def test_zero_state_tax_states(self, client):
        for state in ["TX", "FL", "WA", "NV"]:
            r = client.post("/payroll/calculate", json={
                "pay_type": "salary", "annual_salary": 60000,
                "pay_frequency": "biweekly", "filing_status": "single",
                "state_code": state,
            })
            assert r.status_code == 200
            assert r.json()["state_income_tax"] == 0.0, f"{state} should have 0 state tax"

    def test_no_auth_required(self):
        """Calculator endpoint should work without auth."""
        r = httpx.post(f"{BASE}/payroll/calculate", json={
            "pay_type": "salary", "annual_salary": 50000,
            "pay_frequency": "biweekly", "filing_status": "single",
            "state_code": "NY",
        })
        assert r.status_code == 200


# ── Payroll Preview ────────────────────────────────────────────
class TestPayrollPreview:
    def test_preview_all_employees(self, client):
        r = client.post("/payroll/preview", json={
            "period_start": "2026-03-01",
            "period_end": "2026-03-15",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["preview"] == True
        assert "items" in data
        assert "totals" in data
        assert data["totals"]["gross"] > 0
        assert data["totals"]["net"] < data["totals"]["gross"]

    def test_preview_totals_balance(self, client):
        r = client.post("/payroll/preview", json={
            "period_start": "2026-03-01",
            "period_end": "2026-03-15",
        })
        data = r.json()
        sum_gross = sum(item["gross_pay"] for item in data["items"])
        sum_net = sum(item["net_pay"] for item in data["items"])
        assert abs(sum_gross - data["totals"]["gross"]) < 0.05
        assert abs(sum_net - data["totals"]["net"]) < 0.05


# ── Payroll History ────────────────────────────────────────────
class TestPayrollHistory:
    def test_list_history(self, client):
        r = client.get("/payroll/history")
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data
        assert "total" in data

    def test_history_pagination(self, client):
        r = client.get("/payroll/history?limit=2&skip=0")
        assert r.status_code == 200
        assert len(r.json()["runs"]) <= 2


# ── Reports ────────────────────────────────────────────────────
class TestReports:
    def test_ytd_summary(self, client):
        r = client.get("/reports/ytd-summary")
        assert r.status_code == 200
        data = r.json()
        assert "year" in data
        assert "total_gross" in data
        assert "run_count" in data

    def test_by_department(self, client):
        r = client.get("/reports/by-department")
        assert r.status_code == 200
        assert "departments" in r.json()

    def test_employee_ytd(self, client):
        r = client.get("/reports/employee-ytd")
        assert r.status_code == 200
        assert "employees" in r.json()

    def test_tax_liability(self, client):
        r = client.get("/reports/tax-liability")
        assert r.status_code == 200
        data = r.json()
        assert "irs_941_liability" in data
        assert "total_tax_liability" in data


# ── Export ─────────────────────────────────────────────────────
class TestExport:
    def test_export_employees_csv(self, client):
        r = client.get("/export/employees")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "first_name" in r.text   # CSV header

    def test_export_ytd_csv(self, client):
        r = client.get("/export/employee-ytd")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]

    def test_export_history_csv(self, client):
        r = client.get("/export/payroll-history")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]


# ── Import ─────────────────────────────────────────────────────
class TestImport:
    def test_import_template_download(self, client):
        r = client.get("/import/employees/template")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "first_name" in r.text

    def test_import_dry_run_valid(self, client):
        csv_content = (
            "first_name,last_name,hire_date,pay_type,pay_rate,department,state_code\n"
            "Import,Test,2026-01-01,salary,70000,Engineering,NY\n"
        )
        files = {"file": ("test.csv", csv_content.encode(), "text/csv")}
        r = httpx.post(
            f"{BASE}/import/employees?dry_run=true",
            files=files,
            headers={"Authorization": client.headers["Authorization"]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["dry_run"] == True
        assert data["errors"] == 0

    def test_import_missing_required(self, client):
        csv_content = "first_name,last_name\nMissing,Required\n"
        files = {"file": ("test.csv", csv_content.encode(), "text/csv")}
        r = httpx.post(
            f"{BASE}/import/employees?dry_run=true",
            files=files,
            headers={"Authorization": client.headers["Authorization"]},
        )
        assert r.status_code in (200, 400)  # either error response or 200 with error details


# ── PTO ────────────────────────────────────────────────────────
class TestPTO:
    def test_list_policies(self, client):
        r = client.get("/pto/policies")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_balances(self, client):
        r = client.get("/pto/balances")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_requests(self, client):
        r = client.get("/pto/requests")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── Onboarding ─────────────────────────────────────────────────
class TestOnboarding:
    def test_pending_onboarding(self, client):
        r = client.get("/onboarding/pending")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── Pay Periods ────────────────────────────────────────────────
class TestPayPeriods:
    def test_list_periods(self, client):
        r = client.get("/pay-periods")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_generate_periods(self, client):
        r = client.post("/pay-periods/generate?frequency=biweekly&count=2&start_date=2026-06-01")
        assert r.status_code == 200
        data = r.json()
        assert "created" in data


# ── Rate limiting ──────────────────────────────────────────────
class TestRateLimiting:
    def test_rate_limit_headers_present(self, client):
        r = client.get("/employees")
        assert "x-ratelimit-limit" in r.headers
        assert "x-ratelimit-remaining" in r.headers

    def test_health_not_rate_limited(self):
        for _ in range(5):
            r = httpx.get(f"{BASE}/health")
            assert r.status_code == 200


# ── Users ──────────────────────────────────────────────────────
class TestUsers:
    def test_get_me(self, client):
        r = client.get("/users/me")
        assert r.status_code == 200
        data = r.json()
        assert "email" in data
        assert "role" in data

    def test_list_users(self, client):
        r = client.get("/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ── API Keys ───────────────────────────────────────────────────
class TestApiKeys:
    def test_list_api_keys(self, client):
        r = client.get("/api-keys")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_and_revoke_api_key(self, client):
        r = client.post("/api-keys", json={
            "name": "Integration Test Key",
            "environment": "test",
        })
        assert r.status_code == 201
        data = r.json()
        assert "key" in data
        assert data["key"].startswith("pk_test_")
        key_id = data["id"]

        # Revoke it
        r2 = client.delete(f"/api-keys/{key_id}")
        assert r2.status_code == 204


# ── W-2 ────────────────────────────────────────────────────────
class TestW2:
    def test_get_w2_data(self, client):
        r = client.get("/w2/2026")
        assert r.status_code == 200
        data = r.json()
        assert "year" in data
        assert "w2s" in data

    def test_w2_xml_download(self, client):
        r = client.get("/w2/2026/xml")
        assert r.status_code == 200
        assert "application/xml" in r.headers["content-type"]
