import asyncio
import uuid
from datetime import datetime, timedelta
from jose import jwt
import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb+srv://societypuppet920_db_user:IXdBgsweyQqJBoJa@cluster0.agt82ce.mongodb.net/payrolldb"
    JWT_SECRET: str = "CHANGE_THIS_TO_A_RANDOM_64_CHAR_HEX_STRING"
    JWT_ALGORITHM: str = "HS256"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

def create_token(company_id: str, user_id: str) -> str:
    payload = {
        "company_id": str(company_id),
        "user_id": str(user_id),
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(minutes=60)
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

async def verify():
    # We need a valid company_id that has a QBXpress connection.
    # From the error log, we know some company is trying to sync.
    # Let's try to find one from the database if possible, or just use a dummy one if we can bypass the connection check.
    # But sync_employees requires a connection in the DB.
    
    # I'll try to find a connection in the DB first.
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client.get_default_database()
    
    conn = await db.QBXpressConnection.find_one()
    if not conn:
        print("No QBXpressConnection found in DB")
        return

    company_id = conn["company_id"]
    user_id = str(uuid.uuid4()) # Dummy user_id
    
    token = create_token(company_id, user_id)
    print(f"Generated Token for company {company_id}")
    
    async with httpx.AsyncClient() as http_client:
        resp = await http_client.post(
            "http://localhost:8000/qbxpress/sync/employees",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    asyncio.run(verify())
