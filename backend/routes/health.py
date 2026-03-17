"""
Health check route — verifies connectivity to MongoDB.
Migrated to Beanie (MongoDB).
"""
import time
from fastapi import APIRouter
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check():
    """Verify system health."""
    start_time = time.time()
    
    # Check MongoDB
    mongo_status = "unhealthy"
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=2000)
        await client.admin.command('ping')
        mongo_status = "healthy"
    except Exception as e:
        mongo_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if mongo_status == "healthy" else "degraded",
        "timestamp": time.time(),
        "latency_ms": round((time.time() - start_time) * 1000, 2),
        "db": mongo_status,
        "service": "PayrollOS Backend",
        "version": "1.0.0-mongo"
    }


@router.get("/detailed")
async def health_detailed():
    """Detailed health report for integration tests."""
    from models import Employee, User, Company
    
    start_time = time.time()
    try:
        emp_count = await Employee.count()
        user_count = await User.count()
        company_count = await Company.count()
        db_status = "connected"
    except Exception as e:
        emp_count = user_count = company_count = 0
        db_status = f"error: {str(e)}"

    return {
        "status": "ok" if db_status == "connected" else "error",
        "database": db_status,
        "counts": {
            "employees": emp_count,
            "users": user_count,
            "companies": company_count
        },
        "uptime_seconds": time.time() - start_time # Simplified
    }
