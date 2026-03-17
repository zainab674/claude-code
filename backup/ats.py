"""
Applicant Tracking System (ATS) — lightweight job postings + candidate pipeline.

Jobs:      create/publish/close job postings
Candidates: apply, track pipeline stage, schedule interviews
Pipeline:  Applied → Screening → Interview → Offer → Hired/Rejected

POST /jobs                    create job posting
GET  /jobs                    list all jobs
PUT  /jobs/{id}/publish        publish to careers page
PUT  /jobs/{id}/close          close job posting
POST /jobs/{id}/candidates     add candidate
GET  /jobs/{id}/candidates     list candidates for job
PUT  /candidates/{id}/stage    advance/move pipeline stage
POST /candidates/{id}/notes    add hiring note
GET  /ats/dashboard            hiring funnel stats
"""
import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import (Column, String, Integer, Boolean, Date, DateTime,
                        ForeignKey, Text, select, func)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pydantic import BaseModel
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(tags=["ats"])

PIPELINE_STAGES = [
    "applied", "screening", "phone_screen", "interview",
    "technical", "offer", "hired", "rejected", "withdrawn",
]

JOB_TYPES = ["full_time", "part_time", "contract", "internship"]
WORK_MODES = ["onsite", "remote", "hybrid"]


# ── Models ─────────────────────────────────────────────────────
class JobPosting(Base):
    __tablename__ = "job_postings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    title = Column(String(200), nullable=False)
    department = Column(String(100))
    location = Column(String(200))
    work_mode = Column(String(20), default="onsite")
    job_type = Column(String(20), default="full_time")
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    description = Column(Text)
    requirements = Column(Text)
    benefits_summary = Column(Text)
    status = Column(String(20), default="draft")   # draft|open|closed|filled
    target_hire_date = Column(Date)
    headcount = Column(Integer, default=1)
    filled_count = Column(Integer, default=0)
    hiring_manager_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    posted_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(30))
    linkedin_url = Column(String(500))
    resume_url = Column(String(500))
    stage = Column(String(30), default="applied")
    rating = Column(Integer)             # 1-5 stars
    source = Column(String(50), default="direct")  # linkedin|referral|job_board|direct
    notes = Column(Text)
    tags = Column(JSONB, default=list)
    rejected_reason = Column(String(200))
    offer_amount = Column(Integer)
    offer_date = Column(Date)
    hired_date = Column(Date)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class HiringNote(Base):
    __tablename__ = "hiring_notes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    author_name = Column(String(200))
    note_type = Column(String(30), default="general")  # general|interview|phone_screen|offer
    content = Column(Text, nullable=False)
    rating = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ── Schemas ────────────────────────────────────────────────────
class JobCreate(BaseModel):
    title: str
    department: Optional[str] = None
    location: Optional[str] = None
    work_mode: str = "onsite"
    job_type: str = "full_time"
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    description: Optional[str] = None
    requirements: Optional[str] = None
    benefits_summary: Optional[str] = None
    target_hire_date: Optional[date] = None
    headcount: int = 1
    hiring_manager_id: Optional[str] = None


class CandidateCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    source: str = "direct"
    notes: Optional[str] = None


class StageUpdate(BaseModel):
    stage: str
    notes: Optional[str] = None
    rejected_reason: Optional[str] = None
    offer_amount: Optional[int] = None
    offer_date: Optional[date] = None
    hired_date: Optional[date] = None
    rating: Optional[int] = None


class NoteCreate(BaseModel):
    content: str
    note_type: str = "general"
    rating: Optional[int] = None


# ── Routes: Jobs ───────────────────────────────────────────────
@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    department: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(JobPosting).where(JobPosting.company_id == current_user["company_id"])
    if status:     q = q.where(JobPosting.status == status)
    if department: q = q.where(JobPosting.department == department)
    q = q.order_by(JobPosting.created_at.desc())
    result = await db.execute(q)
    jobs = result.scalars().all()

    # Attach candidate counts
    out = []
    for job in jobs:
        count_res = await db.execute(
            select(func.count(Candidate.id)).where(Candidate.job_id == job.id)
        )
        out.append({**_ser_job(job), "candidate_count": count_res.scalar() or 0})
    return out


@router.post("/jobs", status_code=201)
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = JobPosting(company_id=current_user["company_id"], **body.model_dump())
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return _ser_job(job)


@router.put("/jobs/{job_id}")
async def update_job(
    job_id: str,
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(db, job_id, current_user["company_id"])
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(job, k, v)
    await db.commit()
    await db.refresh(job)
    return _ser_job(job)


@router.put("/jobs/{job_id}/publish")
async def publish_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(db, job_id, current_user["company_id"])
    job.status = "open"
    job.posted_at = datetime.utcnow()
    await db.commit()
    return {"message": "Job published", "status": "open"}


@router.put("/jobs/{job_id}/close")
async def close_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(db, job_id, current_user["company_id"])
    job.status = "closed"
    job.closed_at = datetime.utcnow()
    await db.commit()
    return {"message": "Job closed"}


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(db, job_id, current_user["company_id"])
    await db.delete(job)
    await db.commit()


# ── Routes: Candidates ─────────────────────────────────────────
@router.get("/jobs/{job_id}/candidates")
async def list_candidates(
    job_id: str,
    stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(Candidate).where(
        Candidate.job_id == job_id,
        Candidate.company_id == current_user["company_id"],
    )
    if stage: q = q.where(Candidate.stage == stage)
    q = q.order_by(Candidate.created_at.desc())
    result = await db.execute(q)
    return [_ser_candidate(c) for c in result.scalars().all()]


@router.post("/jobs/{job_id}/candidates", status_code=201)
async def add_candidate(
    job_id: str,
    body: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    await _get_job(db, job_id, current_user["company_id"])
    candidate = Candidate(
        job_id=job_id,
        company_id=current_user["company_id"],
        **body.model_dump(),
    )
    db.add(candidate)
    await db.commit()
    await db.refresh(candidate)
    return _ser_candidate(candidate)


@router.put("/candidates/{candidate_id}/stage")
async def update_stage(
    candidate_id: str,
    body: StageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if body.stage not in PIPELINE_STAGES:
        raise HTTPException(400, f"stage must be: {', '.join(PIPELINE_STAGES)}")
    result = await db.execute(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.company_id == current_user["company_id"],
        )
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Candidate not found")

    c.stage = body.stage
    c.updated_at = datetime.utcnow()
    if body.rating:        c.rating = body.rating
    if body.offer_amount:  c.offer_amount = body.offer_amount
    if body.offer_date:    c.offer_date = body.offer_date
    if body.hired_date:    c.hired_date = body.hired_date
    if body.rejected_reason: c.rejected_reason = body.rejected_reason
    if body.notes:
        c.notes = (c.notes or "") + f"\n[{datetime.utcnow().date()}] {body.notes}"

    # If hired → increment job filled_count
    if body.stage == "hired":
        job_res = await db.execute(select(JobPosting).where(JobPosting.id == c.job_id))
        job = job_res.scalar_one_or_none()
        if job:
            job.filled_count = (job.filled_count or 0) + 1
            if job.filled_count >= job.headcount:
                job.status = "filled"

    await db.commit()
    await db.refresh(c)
    return _ser_candidate(c)


@router.post("/candidates/{candidate_id}/notes", status_code=201)
async def add_note(
    candidate_id: str,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    note = HiringNote(
        candidate_id=candidate_id,
        company_id=current_user["company_id"],
        author_id=current_user["sub"],
        author_name=current_user.get("email", ""),
        **body.model_dump(),
    )
    db.add(note)
    await db.commit()
    return {"message": "Note added"}


@router.get("/candidates/{candidate_id}/notes")
async def get_notes(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(HiringNote)
        .where(HiringNote.candidate_id == candidate_id,
               HiringNote.company_id == current_user["company_id"])
        .order_by(HiringNote.created_at.desc())
    )
    return [
        {"id": str(n.id), "author": n.author_name, "type": n.note_type,
         "content": n.content, "rating": n.rating, "created_at": str(n.created_at)}
        for n in result.scalars().all()
    ]


# ── Routes: Dashboard ──────────────────────────────────────────
@router.get("/ats/dashboard")
async def ats_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Hiring funnel stats."""
    jobs_res = await db.execute(
        select(
            func.count(JobPosting.id).label("total"),
            func.sum((JobPosting.status == "open").cast(Integer)).label("open"),
            func.sum((JobPosting.status == "filled").cast(Integer)).label("filled"),
        ).where(JobPosting.company_id == current_user["company_id"])
    )
    jobs_row = jobs_res.first()

    stage_res = await db.execute(
        select(Candidate.stage, func.count(Candidate.id).label("count"))
        .where(Candidate.company_id == current_user["company_id"])
        .group_by(Candidate.stage)
    )
    by_stage = {r.stage: r.count for r in stage_res.all()}

    total_candidates = sum(by_stage.values())

    return {
        "jobs": {
            "total": jobs_row.total or 0,
            "open": jobs_row.open or 0,
            "filled": jobs_row.filled or 0,
        },
        "pipeline": {
            "total_candidates": total_candidates,
            "by_stage": [
                {"stage": s, "count": by_stage.get(s, 0),
                 "pct": round(by_stage.get(s, 0) / max(total_candidates, 1) * 100, 1)}
                for s in PIPELINE_STAGES
            ],
        },
        "hired_this_year": by_stage.get("hired", 0),
        "offer_acceptance_rate": round(
            by_stage.get("hired", 0) /
            max(by_stage.get("hired", 0) + by_stage.get("rejected", 0), 1) * 100, 1
        ),
    }


# ── Helpers ────────────────────────────────────────────────────
async def _get_job(db, job_id, company_id):
    result = await db.execute(
        select(JobPosting).where(JobPosting.id == job_id, JobPosting.company_id == company_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    return job


def _ser_job(j: JobPosting) -> dict:
    salary = None
    if j.salary_min and j.salary_max:
        salary = f"${j.salary_min:,} – ${j.salary_max:,}"
    elif j.salary_min:
        salary = f"${j.salary_min:,}+"
    return {
        "id": str(j.id), "title": j.title, "department": j.department,
        "location": j.location, "work_mode": j.work_mode, "job_type": j.job_type,
        "salary_range": salary, "salary_min": j.salary_min, "salary_max": j.salary_max,
        "description": j.description, "requirements": j.requirements,
        "status": j.status, "headcount": j.headcount, "filled_count": j.filled_count or 0,
        "target_hire_date": str(j.target_hire_date) if j.target_hire_date else None,
        "posted_at": str(j.posted_at) if j.posted_at else None,
        "created_at": str(j.created_at),
    }


def _ser_candidate(c: Candidate) -> dict:
    return {
        "id": str(c.id), "job_id": str(c.job_id),
        "name": f"{c.first_name} {c.last_name}",
        "first_name": c.first_name, "last_name": c.last_name,
        "email": c.email, "phone": c.phone, "linkedin_url": c.linkedin_url,
        "stage": c.stage, "rating": c.rating, "source": c.source,
        "notes": c.notes, "tags": c.tags or [],
        "offer_amount": c.offer_amount, "offer_date": str(c.offer_date) if c.offer_date else None,
        "hired_date": str(c.hired_date) if c.hired_date else None,
        "created_at": str(c.created_at),
    }
