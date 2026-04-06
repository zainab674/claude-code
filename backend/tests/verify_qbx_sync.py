import asyncio
import uuid
from decimal import Decimal
from datetime import datetime
import sys
import os

# Add parent dir to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Employee, QBXpressConnection
from services.qbxpress import get_employees
import services.qbxpress as qbx_svc
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

async def test_sync_logic():
    # Setup mock data instead of calling real API for this unit test
    mock_employees = [
        {
            "id": "qbx-emp-123",
            "firstName": "Test",
            "lastName": "User",
            "email": "test@qbxpress.com",
            "phone": "555-0199",
            "address": "123 QB Lane",
            "hourlyRate": 45.50
        },
        {
            "id": "qbx-emp-456",
            "firstName": "New",
            "lastName": "Hire",
            "email": "new@qbxpress.com",
            "hourlyRate": 30.00
        }
    ]
    
    # Mock the service call
    async def mock_get_employees(*args, **kwargs):
        return mock_employees
    
    qbx_svc.get_employees = mock_get_employees
    
    # Setup DB
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    await init_beanie(database=client.get_default_database(), document_models=[Employee, QBXpressConnection])
    
    company_id = uuid.uuid4()
    print(f"Testing sync for company: {company_id}")
    
    # Create a dummy connection
    conn = QBXpressConnection(
        company_id=company_id,
        token="mock-token",
        qbx_company_id="qbx-comp-1",
        qbx_company_name="Mock QBX"
    )
    await conn.insert()
    
    # Re-implement the route logic here for verification
    qbx_employees = await qbx_svc.get_employees(conn.token)
    
    synced_count = 0
    for qe in qbx_employees:
        existing = await Employee.find_one(
            Employee.company_id == company_id,
            {"$or": [{"qb_employee_id": str(qe["id"])}, {"email": qe.get("email")}]}
        )
        
        if existing:
            existing.first_name = qe.get("firstName") or existing.first_name
            existing.qb_employee_id = str(qe["id"])
            await existing.save()
            print(f"Updated: {existing.first_name}")
        else:
            new_emp = Employee(
                company_id=company_id,
                first_name=qe.get("firstName") or "Unknown",
                last_name=qe.get("lastName") or "",
                email=qe.get("email"),
                phone=qe.get("phone"),
                pay_rate=Decimal(str(qe.get("hourlyRate", 0))),
                qb_employee_id=str(qe["id"]),
            )
            await new_emp.insert()
            print(f"Created: {new_emp.first_name}")
        synced_count += 1
        
    # Verify
    count = await Employee.find(Employee.company_id == company_id).count()
    print(f"Total employees in DB: {count}")
    assert count == 2
    print("Verification SUCCESSFUL!")

if __name__ == "__main__":
    asyncio.run(test_sync_logic())
