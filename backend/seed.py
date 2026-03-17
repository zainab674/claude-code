"""
Database seeder — creates realistic test data for development.
Migrated to Beanie (MongoDB).
"""
import asyncio
import random
from datetime import date, timedelta, datetime
from decimal import Decimal
import sys
import os
import uuid

# Add current directory to path so we can import local modules
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db
from models import (
    Company, User, Employee, SalaryBand, PtoPolicy, PtoBalance, 
    BenefitPlan, Contractor, ContractorPayment, Notification
)
from utils.auth import hash_password

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
        ("QA Engineer",          Decimal("35.0"), "hourly"),
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
    print("🌱 Starting seed...")
    await init_db()

    # Create Company (Acme Corp)
    company = await Company.find_one(Company.name == "Acme Corp")
    if not company:
        company = Company(
            name="Acme Corp",
            ein="12-3456789",
            address_line1="123 Tech Lane",
            city="New York",
            state="NY",
            zip="10001",
            email="hr@acmecorp.com"
        )
        await company.insert()
        print(f"  Created Company: {company.id}")
    else:
        print(f"  Company exists: {company.id}")

    # Create Admin User
    admin = await User.find_one(User.email == "admin@acme.com")
    if not admin:
        admin = User(
            company_id=company.id,
            email="admin@acme.com",
            password_hash=hash_password("Admin123!"),
            first_name="Admin",
            last_name="User",
            role="admin"
        )
        await admin.insert()
        print("  Created Admin: admin@acme.com")

    # Seed Employees
    emp_count = await Employee.find(Employee.company_id == company.id).count()
    if emp_count < 5:
        await _seed_employees(company.id)
    else:
        print(f"  Found {emp_count} employees. Skipping employee seeding.")

    await _seed_salary_bands(company.id)
    await _seed_pto_policy(company.id)
    await _seed_benefit_plans(company.id)
    await _seed_contractors(company.id)
    await _seed_notifications(company.id)

    print("\n✅ Seed complete!")
    print("   Login: admin@acme.com / Admin123!")


async def _seed_employees(company_id):
    print("\n  Creating 25 employees...")
    used_names = set()
    created = 0

    for dept, roles in DEPARTMENTS.items():
        n = random.randint(3, 5)
        for i in range(n):
            role = random.choice(roles)
            for _ in range(50):
                fn = random.choice(FIRST_NAMES)
                ln = random.choice(LAST_NAMES)
                if (fn, ln) not in used_names:
                    used_names.add((fn, ln))
                    break

            hire_date = date.today() - timedelta(days=random.randint(30, 1200))
            
            emp = Employee(
                company_id=company_id,
                first_name=fn,
                last_name=ln,
                email=f"{fn.lower()}.{ln.lower()}@acmecorp.com",
                hire_date=hire_date,
                pay_type=role[2],
                pay_rate=Decimal(str(role[1])),
                department=dept,
                job_title=role[0],
                filing_status=random.choice(FILING_STATUSES),
                state_code=random.choice(STATES),
                health_insurance_deduction=Decimal("250") if role[2] == "salary" else Decimal("0"),
                dental_deduction=Decimal("25") if role[2] == "salary" else Decimal("0"),
                vision_deduction=Decimal("10") if role[2] == "salary" else Decimal("0"),
                retirement_401k_pct=Decimal(str(round(random.choice([0, 0.03, 0.04, 0.05]), 2)))
            )
            await emp.insert()
            created += 1
            if created >= 25: break
        if created >= 25: break

    print(f"  Created {created} employees")


async def _seed_salary_bands(company_id):
    count = await SalaryBand.find(SalaryBand.company_id == company_id).count()
    if count > 0: return
    
    print("\n  Creating salary bands...")
    bands = [
        ("Software Engineer I",  "Engineering", "IC1", 80000, 92500, 105000),
        ("Software Engineer II", "Engineering", "IC2", 100000, 117500, 135000),
        ("Senior Engineer",      "Engineering", "IC3", 130000, 150000, 170000),
        ("Staff Engineer",       "Engineering", "IC4", 155000, 180000, 210000),
        ("Engineering Manager",  "Engineering", "M1",  145000, 165000, 185000),
        ("Product Manager",      "Product",     "IC2", 115000, 130000, 148000),
        ("UI/UX Designer",       "Design",      "IC1", 82000, 97000, 112000),
    ]
    for jt, dept, lvl, mn, mid, mx in bands:
        band = SalaryBand(
            company_id=company_id,
            job_title=jt,
            department=dept,
            level=lvl,
            min_salary=Decimal(str(mn)),
            mid_salary=Decimal(str(mid)),
            max_salary=Decimal(str(mx))
        )
        await band.insert()
    print(f"  Created {len(bands)} salary bands")


async def _seed_pto_policy(company_id):
    count = await PtoPolicy.find(PtoPolicy.company_id == company_id).count()
    if count > 0: return
    
    print("\n  Creating PTO policy + balances...")
    policy = PtoPolicy(
        company_id=company_id,
        name="Standard PTO",
        accrual_rate=Decimal("3.08"),
        max_accrual=Decimal("240"),
        carryover_limit=Decimal("80")
    )
    await policy.insert()

    employees = await Employee.find(Employee.company_id == company_id).to_list()
    for emp in employees:
        balance = Decimal(str(round(random.uniform(20, 120), 1)))
        used = Decimal(str(round(random.uniform(0, 40), 1)))
        pb = PtoBalance(
            employee_id=emp.id,
            company_id=company_id,
            policy_id=policy.id,
            available_hours=balance,
            used_hours=used,
            ytd_accrued=balance + used
        )
        await pb.insert()
    print(f"  Created balances for {len(employees)} employees")


async def _seed_benefit_plans(company_id):
    count = await BenefitPlan.find(BenefitPlan.company_id == company_id).count()
    if count > 0: return
    
    print("\n  Creating benefit plans...")
    plans = [
        ("health", "Acme Blue Shield PPO", "Blue Shield", 320, 450),
        ("dental", "Acme Dental Plus",     "Delta Dental", 28, 42),
        ("vision", "Acme Vision Care",     "VSP",          12, 18),
        ("401k",   "Acme 401(k)",          "Fidelity",      0, 0),
    ]
    for pt, pn, cr, ec, erc in plans:
        plan = BenefitPlan(
            company_id=company_id,
            plan_type=pt,
            plan_name=pn,
            carrier=cr,
            employee_cost_per_period=Decimal(str(ec)),
            employer_cost_per_period=Decimal(str(erc))
        )
        await plan.insert()
    print(f"  Created {len(plans)} plans")


async def _seed_contractors(company_id):
    count = await Contractor.find(Contractor.company_id == company_id).count()
    if count > 0: return
    
    print("\n  Creating contractors...")
    contractors = [
        ("Acme Design Studio", "individual", 8500),
        ("TechWriters Inc",    "business",   3200),
    ]
    for name, ct, total in contractors:
        parts = name.split()
        fn, ln = parts[0], parts[-1]
        c = Contractor(
            company_id=company_id,
            first_name=fn,
            last_name=ln,
            business_name=name,
            contractor_type=ct,
            email=f"billing@{fn.lower()}.com"
        )
        await c.insert()
        
        # Payment
        p = ContractorPayment(
            contractor_id=c.id,
            company_id=company_id,
            payment_date=date.today() - timedelta(days=30),
            amount=Decimal(str(total)),
            tax_year=date.today().year
        )
        await p.insert()
    print(f"  Created {len(contractors)} contractors")


async def _seed_notifications(company_id):
    count = await Notification.find(Notification.company_id == company_id).count()
    if count > 0: return
    
    print("\n  Creating notifications...")
    notifs = [
        ("compliance", "Compliance Alert", "2 employees missing tax codes", "warning"),
        ("pto_request", "PTO Request", "Sarah Chen requested 3 days", "info")
    ]
    for nt, title, body, sev in notifs:
        n = Notification(
            company_id=company_id,
            type=nt,
            title=title,
            body=body,
            severity=sev
        )
        await n.insert()


if __name__ == "__main__":
    asyncio.run(seed())
