"""
Load testing with Locust.
Tests all major API endpoints under concurrent load.

Install: pip install locust
Run:     locust -f locustfile.py --host=http://localhost:8000
Web UI:  http://localhost:8089

Or headless:
  locust -f locustfile.py --host=http://localhost:8000 \
    --users=50 --spawn-rate=5 --run-time=60s --headless
"""
import json
import random
from locust import HttpUser, task, between, events


# ── Auth fixture ───────────────────────────────────────────────
class PayrollUser(HttpUser):
    wait_time = between(0.5, 2.0)
    token = None
    company_id = None
    employee_ids = []

    def on_start(self):
        """Login once per virtual user."""
        resp = self.client.post("/auth/login", json={
            "email": "admin@acme.com",
            "password": "Admin123!",
        })
        if resp.status_code == 200:
            data = resp.json()
            self.token = data["access_token"]
            self.company_id = data["user"]["company_id"]
            self.client.headers["Authorization"] = f"Bearer {self.token}"
            # Cache employee IDs for later tasks
            emp_resp = self.client.get("/employees?status=active&limit=50")
            if emp_resp.status_code == 200:
                self.employee_ids = [e["id"] for e in emp_resp.json().get("employees", [])]

    # ── Read-heavy endpoints ───────────────────────────────────
    @task(10)
    def get_employees(self):
        self.client.get("/employees", name="/employees")

    @task(8)
    def payroll_history(self):
        self.client.get("/payroll/history?limit=10", name="/payroll/history")

    @task(6)
    def ytd_summary(self):
        self.client.get("/reports/ytd-summary", name="/reports/ytd-summary")

    @task(5)
    def notifications(self):
        self.client.get("/notifications?limit=20", name="/notifications")

    @task(4)
    def compliance_check(self):
        self.client.get("/compliance/pre-payroll", name="/compliance/pre-payroll")

    @task(3)
    def health_check(self):
        self.client.get("/health/detailed", name="/health/detailed")

    @task(3)
    def dashboard_reports(self):
        self.client.get("/reports/by-department", name="/reports/by-department")
        self.client.get("/reports/tax-liability", name="/reports/tax-liability")

    @task(2)
    def pto_balances(self):
        self.client.get("/pto/balances", name="/pto/balances")

    @task(2)
    def pay_periods(self):
        self.client.get("/pay-periods?limit=12", name="/pay-periods")

    # ── Write endpoints ────────────────────────────────────────
    @task(2)
    def payroll_preview(self):
        today = "2026-03-01"
        end = "2026-03-15"
        self.client.post("/payroll/preview", json={
            "period_start": today,
            "period_end": end,
            "hours_overrides": [],
        }, name="/payroll/preview")

    @task(2)
    def payroll_calculate(self):
        """Public endpoint — no auth needed, high traffic expected."""
        self.client.post("/payroll/calculate", json={
            "pay_type": "salary",
            "annual_salary": random.choice([60000, 75000, 90000, 120000, 150000]),
            "pay_frequency": "biweekly",
            "filing_status": random.choice(["single", "married"]),
            "state_code": random.choice(["NY", "CA", "TX", "WA"]),
        }, name="/payroll/calculate")

    @task(1)
    def search_employees(self):
        queries = ["Sarah", "Eng", "Design", "senior"]
        self.client.get(f"/employees?search={random.choice(queries)}", name="/employees?search=")

    @task(1)
    def get_single_employee(self):
        if self.employee_ids:
            emp_id = random.choice(self.employee_ids)
            self.client.get(f"/employees/{emp_id}", name="/employees/{id}")

    @task(1)
    def export_employees(self):
        self.client.get("/export/employees", name="/export/employees")

    @task(1)
    def w2_data(self):
        self.client.get("/w2/2026", name="/w2/{year}")

    @task(1)
    def audit_log(self):
        self.client.get("/audit?limit=20", name="/audit")


# ── Calculator-only user (simulates public widget traffic) ─────
class CalculatorUser(HttpUser):
    """Simulates high traffic to the public calculator endpoint."""
    wait_time = between(0.1, 1.0)
    weight = 3   # 3x more calculator users than admin users

    @task
    def calculate(self):
        self.client.post("/payroll/calculate", json={
            "pay_type": random.choice(["salary", "hourly"]),
            "annual_salary": random.randint(40000, 200000),
            "hourly_rate": round(random.uniform(15, 80), 2),
            "pay_frequency": random.choice(["weekly", "biweekly", "monthly"]),
            "filing_status": random.choice(["single", "married", "head_of_household"]),
            "state_code": random.choice(["NY", "CA", "TX", "FL", "WA", "IL", "MA"]),
            "regular_hours": 80,
            "overtime_hours": random.choice([0, 0, 0, 5, 10]),
            "health_insurance": random.choice([0, 150, 300]),
            "retirement_401k_pct": random.choice([0, 0.03, 0.05, 0.06]),
        }, name="/payroll/calculate [public]")

    @task(5)
    def health(self):
        self.client.get("/health", name="/health")


# ── Event hooks ────────────────────────────────────────────────
@events.test_start.add_listener
def on_start(environment, **kwargs):
    print("\n" + "="*60)
    print("  PayrollOS Load Test Starting")
    print("  Target: API performance under concurrent load")
    print("  SLA: p95 < 500ms, p99 < 1000ms, error rate < 0.1%")
    print("="*60 + "\n")


@events.test_stop.add_listener
def on_stop(environment, **kwargs):
    stats = environment.stats
    total = stats.total
    print("\n" + "="*60)
    print("  Load Test Results")
    print(f"  Total requests:    {total.num_requests:,}")
    print(f"  Failures:          {total.num_failures:,} ({total.fail_ratio:.1%})")
    print(f"  Median response:   {total.median_response_time}ms")
    print(f"  95th percentile:   {total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  99th percentile:   {total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Avg RPS:           {total.current_rps:.1f}")
    print("="*60 + "\n")

    sla_ok = (
        total.fail_ratio < 0.001 and
        total.get_response_time_percentile(0.95) < 500 and
        total.get_response_time_percentile(0.99) < 1000
    )
    print(f"  SLA: {'✅ PASSED' if sla_ok else '❌ FAILED'}\n")
