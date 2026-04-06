import asyncio
import uuid
from decimal import Decimal
import sys
import os

# Add parent dir to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PayRunItem, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

async def verify_fix():
    print("Verifying fix for 'total_employer_taxes'...")
    
    # Setup DB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(database=client.get_default_database(), document_models=[PayRunItem])
    
    # Create a mock item
    item = PayRunItem(
        pay_run_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        total_employee_taxes=Decimal("100.50"),
        total_employer_taxes=Decimal("50.25")
    )
    
    print(f"Item total_employee_taxes: {item.total_employee_taxes}")
    print(f"Item total_employer_taxes: {item.total_employer_taxes}")
    
    items = [item]
    
    # Replicate the logic from the route
    try:
        total_tax = sum(float(i.total_employee_taxes or 0) + float(i.total_employer_taxes or 0) for i in items)
        print(f"Calculated total_tax: {total_tax}")
        assert total_tax == 150.75
        print("Verification SUCCESSFUL!")
    except AttributeError as e:
        print(f"Verification FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_fix())
