from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from config import settings
import models

async def init_db():
    client = AsyncIOMotorClient(settings.MONGODB_URL, uuidRepresentation='standard')
    await init_beanie(
        database=client.get_default_database(),
        document_models=[
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
            models.OnboardingTask,
            models.EmployeeDocument,
            models.BankAccount,
            models.LeaveRecord,
            models.ReviewCycle,
            models.PerformanceReview,
            models.ReviewGoal,
            models.Expense,
            models.GarnishmentOrder,
            models.JobPosting,
            models.Candidate,
            models.HiringNote,
            models.ApiKey,
            models.EmployeeUserLink,
            models.ScheduleConfig,
            models.CustomFieldSchema,
            models.CustomFieldValue,
            models.PayrollAdjustment,
        ]
    )


async def get_db():
    """No-op for backward compatibility during migration."""
    yield None
