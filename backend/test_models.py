import asyncio
import uuid
from datetime import date, datetime
from decimal import Decimal
import models
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

async def test_all_models():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.test_db
    all_models = [
        models.Company,
        models.User,
        models.Employee,
        models.PayPeriod,
        models.PayRun,
        models.PayRunItem,
        models.Paystub,
        models.TimeEntry,
        models.SalaryBand,
        models.PtoPolicy,
        models.PtoBalance,
        models.PtoRequest,
        models.BenefitPlan,
        models.EnrollmentWindow,
        models.BenefitElection,
        models.Contractor,
        models.ContractorPayment,
        models.Notification,
        models.AuditLog,
    ]
    await init_beanie(database=db, document_models=all_models)
    
    print("Test Company")
    try:
        models.Company(name="Test", ein="123")
    except Exception as e:
        print(f"Company failed: {e}")

    print("Test Employee")
    try:
        models.Employee(
            company_id=uuid.uuid4(),
            first_name="John",
            last_name="Doe",
            pay_rate=Decimal("50000")
        )
    except Exception as e:
        print(f"Employee failed: {e}")

    print("Test User")
    try:
        models.User(
            company_id=uuid.uuid4(),
            email="test@test.com",
            password_hash="hash"
        )
    except Exception as e:
        print(f"User failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_all_models())
