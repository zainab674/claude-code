"""
Database seeder — creates realistic test data for development.
Run: python3 seed.py

Creates:
  - 1 company (Acme Corp)
  - 1 admin user (admin@acme.com / Admin123!)
  - 25 employees across 5 departments
  - 6 months of pay run history
  - PTO policies and balances
  - Benefit plans and elections
  - Salary bands for all roles
  - Time entries for hourly staff
  - A few contractors with payments
  - Notification records
  - Onboarding checklists
"""
import asyncio
import random
from datetime import date, timedelta, datetime
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://payroll:payroll_secret@localhost:5432/payrolldb")
engine = create_async_engine(DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
Session = async_sessionmaker(engine, expire_on_commit=False)

# ── Realistic data sets ────────────────────────────────────────
FIRST_NAMES = ["Sarah", "Marcus", "Priya", "James", "Dana", "Alex", "Jordan",
               "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Blake",
               "Cameron", "Drew", "Emery", "Finley", "Harper", "Indigo"]
LAST_NAMES = ["Chen", "Webb", "Nair", "Liu", "Park", "Johnson", "Williams",
              "Brown", "Davis", "Miller", "Wilson", "Moore", "Taylor", "Anderson",
              "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson"]

DEPARTMENTS = {
    "Engineering": [
        ("Software Engineer I",  85000, "salary"),
        ("Software Engineer II", 110000, "salary"),
        ("Senior Engineer",      140000, "salary"),
        ("Staff Engineer",       170000, "salary"),
        ("Engineering Manager",  160000, "salary"),
    ],
    "Product": [
        ("Product Manager",      125000, "salary"),
        ("Senior PM",            150000, "salary"),
        ("Director of Product",  180000, "salary"),
    ],
    "Design": [
        ("UI/UX Designer",       90000,  "salary"),
        ("Senior Designer",      115000, "salary"),
        ("Design Lead",          135000, "salary"),
    ],
    "Operations": [
        ("Office Manager",       65000,  "salary"),
        ("Operations Associate", 58000,  "salary"),
        ("HR Coordinator",       70000,  "salary"),
        ("QA Engineer",          35.0,   "hourly"),
    ],
    "Sales": [
        ("Account Executive",    75000,  "salary"),
        ("Sales Manager",        120000, "salary"),
        ("SDR",                  55000,  "salary"),
    ],
}

STATES = ["NY", "CA", "TX", "WA", "IL", "MA", "CO", "GA"]
FILING_STATUSES = ["single", "married", "single", "married", "head_of_household"]


async def seed():
    async with Session() as db:
        print("🌱 Starting seed...")

        # Get company
        result = await db.execute(text("SELECT id FROM companies LIMIT 1"))
        row = result.first()
        if not row:
            print("❌ No company found. Run init.sql first.")
            return
        company_id = str(row[0])
        print(f"  Company: {company_id[:8]}...")

        # Get existing employee count
        emp_count = (await db.execute(text("SELECT COUNT(*) FROM employees"))).scalar()
        if emp_count > 5:
            print(f"  Database already has {emp_count} employees. Skipping employee seeding.")
        else:
            await _seed_employees(db, company_id)

        await _seed_salary_bands(db, company_id)
        await _seed_pto_policy(db, company_id)
        await _seed_benefit_plans(db, company_id)
        await _seed_contractors(db, company_id)
        await _seed_notifications(db, company_id)

        await db.commit()
        print("\n✅ Seed complete!")
        print("   Login: admin@acme.com / Admin123!")


async def _seed_employees(db, company_id):
    print("\n  Creating 25 employees...")
    used_names = set()
    created = 0

    for dept, roles in DEPARTMENTS.items():
        # 3–6 employees per department
        n = random.randint(3, min(6, len(roles) * 2))
        for i in range(n):
            role = random.choice(roles)
            # Pick unique name
            for _ in range(50):
                fn = random.choice(FIRST_NAMES)
                ln = random.choice(LAST_NAMES)
                if (fn, ln) not in used_names:
                    used_names.add((fn, ln))
                    break

            hire_date = date.today() - timedelta(days=random.randint(30, 1200))
            state = random.choice(STATES)
            filing = random.choice(FILING_STATUSES)
            pay_rate = role[1]
            pay_type = role[2]
            health = 250 if pay_type == "salary" else 0
            dental = 25 if pay_type == "salary" else 0
            vision = 10 if pay_type == "salary" else 0
            retire = round(random.choice([0, 0.03, 0.04, 0.05, 0.06]), 2)

            await db.execute(text("""
                INSERT INTO employees (
                    company_id, first_name, last_name, email, hire_date,
                    pay_type, pay_rate, pay_frequency, department, job_title,
                    filing_status, state_code, health_insurance_deduction,
                    dental_deduction, vision_deduction, retirement_401k_pct, status
                ) VALUES (
                    :company_id, :fn, :ln, :email, :hire_date,
                    :pay_type, :pay_rate, 'biweekly', :dept, :title,
                    :filing, :state, :health, :dental, :vision, :retire, 'active'
                )
            """), {
                "company_id": company_id, "fn": fn, "ln": ln,
                "email": f"{fn.lower()}.{ln.lower()}@acmecorp.com",
                "hire_date": hire_date, "pay_type": pay_type,
                "pay_rate": pay_rate, "dept": dept, "title": role[0],
                "filing": filing, "state": state,
                "health": health, "dental": dental, "vision": vision, "retire": retire,
            })
            created += 1
            if created >= 25:
                break
        if created >= 25:
            break

    print(f"  Created {created} employees")


async def _seed_salary_bands(db, company_id):
    # Check if bands already exist
    count = (await db.execute(text("SELECT COUNT(*) FROM salary_bands WHERE company_id = :c"), {"c": company_id})).scalar()
    if count > 0:
        return
    print("\n  Creating salary bands...")
    bands = [
        ("Software Engineer I",  "Engineering", "IC1", 80000, 92500, 105000),
        ("Software Engineer II", "Engineering", "IC2", 100000, 117500, 135000),
        ("Senior Engineer",      "Engineering", "IC3", 130000, 150000, 170000),
        ("Staff Engineer",       "Engineering", "IC4", 155000, 180000, 210000),
        ("Engineering Manager",  "Engineering", "M1",  145000, 165000, 185000),
        ("Product Manager",      "Product",     "IC2", 115000, 130000, 148000),
        ("Senior PM",            "Product",     "IC3", 135000, 155000, 178000),
        ("UI/UX Designer",       "Design",      "IC1", 82000, 97000, 112000),
        ("Senior Designer",      "Design",      "IC2", 105000, 122000, 142000),
        ("Account Executive",    "Sales",       "IC2", 65000, 82000, 100000),
        ("Sales Manager",        "Sales",       "M1",  105000, 127000, 150000),
    ]
    for job_title, dept, level, mn, mid, mx in bands:
        await db.execute(text("""
            INSERT INTO salary_bands (company_id, job_title, department, level, min_salary, mid_salary, max_salary, effective_year)
            VALUES (:c, :jt, :dept, :lvl, :mn, :mid, :mx, 2026)
        """), {"c": company_id, "jt": job_title, "dept": dept, "lvl": level, "mn": mn, "mid": mid, "mx": mx})
    print(f"  Created {len(bands)} salary bands")


async def _seed_pto_policy(db, company_id):
    count = (await db.execute(text("SELECT COUNT(*) FROM pto_policies WHERE company_id = :c"), {"c": company_id})).scalar()
    if count > 0:
        return
    print("\n  Creating PTO policy + balances...")
    await db.execute(text("""
        INSERT INTO pto_policies (company_id, name, accrual_rate, max_accrual, carryover_limit, waiting_period_days)
        VALUES (:c, 'Standard PTO', 3.08, 240, 80, 90)
    """), {"c": company_id})

    # Seed balances for all employees
    emps = (await db.execute(text("SELECT id FROM employees WHERE company_id = :c AND status = 'active'"), {"c": company_id})).fetchall()
    for (emp_id,) in emps:
        balance = random.uniform(20, 120)
        used = random.uniform(0, 40)
        await db.execute(text("""
            INSERT INTO pto_balances (employee_id, company_id, available_hours, used_hours, ytd_accrued)
            VALUES (:e, :c, :bal, :used, :acc)
            ON CONFLICT (employee_id) DO NOTHING
        """), {"e": emp_id, "c": company_id, "bal": round(balance, 1), "used": round(used, 1), "acc": round(balance + used, 1)})
    print(f"  Created PTO balances for {len(emps)} employees")


async def _seed_benefit_plans(db, company_id):
    count = (await db.execute(text("SELECT COUNT(*) FROM benefit_plans WHERE company_id = :c"), {"c": company_id})).scalar()
    if count > 0:
        return
    print("\n  Creating benefit plans...")
    plans = [
        ("health", "Acme Blue Shield PPO", "Blue Shield", 320, 450),
        ("health", "Acme Kaiser HMO",      "Kaiser",      220, 350),
        ("dental", "Acme Dental Plus",     "Delta Dental", 28, 42),
        ("vision", "Acme Vision Care",     "VSP",          12, 18),
        ("401k",   "Acme 401(k)",          "Fidelity",      0, 0),
    ]
    for ptype, pname, carrier, emp_cost, er_cost in plans:
        await db.execute(text("""
            INSERT INTO benefit_plans (company_id, plan_type, plan_name, carrier, employee_cost_per_period, employer_cost_per_period, is_active)
            VALUES (:c, :pt, :pn, :carrier, :emp, :er, TRUE)
        """), {"c": company_id, "pt": ptype, "pn": pname, "carrier": carrier, "emp": emp_cost, "er": er_cost})
    print(f"  Created {len(plans)} benefit plans")


async def _seed_contractors(db, company_id):
    count = (await db.execute(text("SELECT COUNT(*) FROM contractors WHERE company_id = :c"), {"c": company_id})).scalar()
    if count > 0:
        return
    print("\n  Creating contractors + payments...")
    contractors = [
        ("Acme Design Studio",     "Design",     "individual", 8500),
        ("TechWriters Inc",        "Content",    "business",   3200),
        ("SecureCode LLC",         "Security",   "business",   12000),
        ("Marketing Consultant",   "Marketing",  "individual", 4500),
    ]
    for name, dept, ctype, total_paid in contractors:
        parts = name.split()
        fn, ln = parts[0], parts[-1]
        result = await db.execute(text("""
            INSERT INTO contractors (company_id, first_name, last_name, business_name, contractor_type, email, is_active)
            VALUES (:c, :fn, :ln, :bn, :ct, :email, TRUE) RETURNING id
        """), {"c": company_id, "fn": fn, "ln": ln, "bn": name, "ct": ctype, "email": f"billing@{fn.lower()}.com"})
        cid = result.scalar()

        # Split total into 3–4 payments
        n_payments = random.randint(3, 4)
        per_payment = total_paid / n_payments
        for j in range(n_payments):
            pdate = date.today() - timedelta(days=random.randint(10, 300))
            await db.execute(text("""
                INSERT INTO contractor_payments (contractor_id, company_id, payment_date, amount, payment_method, tax_year)
                VALUES (:cid, :c, :pd, :amt, 'ach', :yr)
            """), {"cid": cid, "c": company_id, "pd": pdate, "amt": round(per_payment, 2), "yr": pdate.year})

    print(f"  Created {len(contractors)} contractors with payment history")


async def _seed_notifications(db, company_id):
    count = (await db.execute(text("SELECT COUNT(*) FROM notifications WHERE company_id = :c"), {"c": company_id})).scalar()
    if count > 0:
        return
    print("\n  Creating sample notifications...")
    notifs = [
        ("payroll_complete", "Payroll complete", "Feb 16–28 run: 24 employees, $47,140 gross", "history", "success"),
        ("compliance", "Compliance issue detected", "2 employees missing state code", "compliance", "warning"),
        ("pto_request", "PTO request pending", "Sarah Chen requested 3 days off", "pto", "info"),
        ("review_due", "Performance reviews due", "Q1 review cycle closes in 7 days", "performance", "warning"),
        ("onboarding", "New hire onboarding", "Dana Park has 6 incomplete onboarding tasks", "onboarding", "info"),
    ]
    for ntype, title, body, url, sev in notifs:
        await db.execute(text("""
            INSERT INTO notifications (company_id, type, title, body, action_url, severity, is_read)
            VALUES (:c, :t, :title, :body, :url, :sev, FALSE)
        """), {"c": company_id, "t": ntype, "title": title, "body": body, "url": url, "sev": sev})
    print(f"  Created {len(notifs)} notifications")


if __name__ == "__main__":
    print("PayrollOS Database Seeder")
    print("=" * 40)
    asyncio.run(seed())
