"""
Background tasks that run after a payroll run completes.
Called via FastAPI BackgroundTasks — non-blocking, runs after response sent.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from config import settings
from models import PayRun, PayRunItem, PayPeriod, Paystub, Employee, Company, User
from services.pdf_generator import generate_paystub_pdf
from services.email import send_paystub_notification, send_payroll_complete_notification
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)

# Create a dedicated async engine for background tasks
_engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_size=3,
)
_Session = async_sessionmaker(_engine, expire_on_commit=False)


async def generate_paystub_pdfs_and_notify(pay_run_id: str):
    """
    Background task triggered after POST /payroll/run completes:
    1. Load all paystubs for the run
    2. Generate PDF for each
    3. Email each employee their paystub
    4. Email admin the run summary
    """
    async with _Session() as db:
        try:
            # Load the pay run
            run_result = await db.execute(select(PayRun).where(PayRun.id == pay_run_id))
            run = run_result.scalar_one_or_none()
            if not run:
                logger.error(f"Pay run {pay_run_id} not found in background task")
                return

            # Load company
            co_result = await db.execute(select(Company).where(Company.id == run.company_id))
            company = co_result.scalar_one()

            # Load pay period
            pp_result = await db.execute(select(PayPeriod).where(PayPeriod.id == run.pay_period_id))
            pay_period = pp_result.scalar_one()

            # Load all paystubs for this run
            stubs_result = await db.execute(
                select(Paystub).where(Paystub.pay_run_id == pay_run_id)
            )
            stubs = stubs_result.scalars().all()

            generated_count = 0
            for stub in stubs:
                try:
                    # Load item + employee
                    item_result = await db.execute(
                        select(PayRunItem).where(PayRunItem.id == stub.pay_run_item_id)
                    )
                    item = item_result.scalar_one()

                    emp_result = await db.execute(
                        select(Employee).where(Employee.id == stub.employee_id)
                    )
                    emp = emp_result.scalar_one()

                    # Build flat dicts for PDF generator
                    emp_dict = {
                        "id": str(emp.id),
                        "first_name": emp.first_name,
                        "last_name": emp.last_name,
                        "job_title": emp.job_title or "",
                        "department": emp.department or "",
                    }
                    co_dict = {
                        "name": company.name,
                        "ein": company.ein or "",
                        "address_line1": company.address_line1 or "",
                        "city": company.city or "",
                        "state": company.state or "",
                        "zip": company.zip or "",
                    }
                    pp_dict = {
                        "period_start": str(pay_period.period_start),
                        "period_end": str(pay_period.period_end),
                        "pay_date": str(pay_period.pay_date),
                    }
                    item_dict = {
                        "regular_pay": float(item.regular_pay or 0),
                        "overtime_pay": float(item.overtime_pay or 0),
                        "bonus_pay": float(item.bonus_pay or 0),
                        "commission_pay": float(item.commission_pay or 0),
                        "reimbursement": float(item.reimbursement or 0),
                        "gross_pay": float(item.gross_pay or 0),
                        "regular_hours": float(item.regular_hours or 0),
                        "overtime_hours": float(item.overtime_hours or 0),
                        "health_insurance": float(item.health_insurance or 0),
                        "dental_insurance": float(item.dental_insurance or 0),
                        "vision_insurance": float(item.vision_insurance or 0),
                        "retirement_401k": float(item.retirement_401k or 0),
                        "hsa": float(item.hsa or 0),
                        "total_pretax_deductions": float(item.total_pretax_deductions or 0),
                        "federal_income_tax": float(item.federal_income_tax or 0),
                        "state_income_tax": float(item.state_income_tax or 0),
                        "local_income_tax": float(item.local_income_tax or 0),
                        "social_security_tax": float(item.social_security_tax or 0),
                        "medicare_tax": float(item.medicare_tax or 0),
                        "additional_medicare_tax": float(item.additional_medicare_tax or 0),
                        "total_employee_taxes": float(item.total_employee_taxes or 0),
                        "employer_social_security": float(item.employer_social_security or 0),
                        "employer_medicare": float(item.employer_medicare or 0),
                        "futa_tax": float(item.futa_tax or 0),
                        "total_employer_taxes": float(item.total_employer_taxes or 0),
                        "garnishment": float(item.garnishment or 0),
                        "total_posttax_deductions": float(item.total_posttax_deductions or 0),
                        "net_pay": float(item.net_pay or 0),
                        "ytd_gross": float(item.ytd_gross or 0),
                        "ytd_federal_tax": float(item.ytd_federal_tax or 0),
                        "ytd_social_security": float(item.ytd_social_security or 0),
                        "ytd_medicare": float(item.ytd_medicare or 0),
                        "ytd_net": float(item.ytd_net or 0),
                    }

                    # Generate PDF
                    pdf_path = generate_paystub_pdf(
                        employee=emp_dict,
                        company=co_dict,
                        pay_period=pp_dict,
                        pay_item=item_dict,
                    )

                    # Update paystub record with path
                    stub.pdf_path = pdf_path
                    stub.pdf_generated_at = datetime.utcnow()
                    generated_count += 1

                    # Email employee if they have an email
                    if emp.email:
                        send_paystub_notification(
                            employee_email=emp.email,
                            employee_name=f"{emp.first_name} {emp.last_name}",
                            company_name=company.name,
                            pay_date=str(pay_period.pay_date),
                            net_pay=float(item.net_pay or 0),
                            pdf_path=pdf_path,
                        )

                except Exception as e:
                    logger.error(f"Error generating paystub for stub {stub.id}: {e}")
                    continue

            await db.commit()
            logger.info(f"Generated {generated_count} paystubs for run {pay_run_id}")

            # Email admin the summary
            admin_result = await db.execute(
                select(User).where(
                    User.company_id == run.company_id,
                    User.role == "admin",
                    User.is_active == True,
                ).limit(1)
            )
            admin = admin_result.scalar_one_or_none()
            if admin and admin.email:
                period_str = f"{pay_period.period_start} – {pay_period.period_end}"
                send_payroll_complete_notification(
                    admin_email=admin.email,
                    company_name=company.name,
                    pay_period=period_str,
                    employee_count=run.employee_count,
                    total_gross=float(run.total_gross or 0),
                    total_net=float(run.total_net or 0),
                    pay_run_id=pay_run_id,
                )

        except Exception as e:
            logger.error(f"Background task error for run {pay_run_id}: {e}")
            import traceback
            traceback.print_exc()


def schedule_pdf_generation(pay_run_id: str):
    """
    Synchronous wrapper to schedule async background task.
    Called from FastAPI BackgroundTasks.add_task().
    """
    asyncio.create_task(generate_paystub_pdfs_and_notify(pay_run_id))
