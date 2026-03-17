import uuid
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from models import JobPosting, Candidate, HiringNote
from utils.auth import get_current_user
from uuid import UUID

router = APIRouter(tags=["ats"])

PIPELINE_STAGES = [
    "applied", "screening", "phone_screen", "interview",
    "technical", "offer", "hired", "rejected", "withdrawn",
]


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
    current_user: dict = Depends(get_current_user),
):
    query = {"company_id": current_user["company_id"]}
    if status:     query["status"] = status
    if department: query["department"] = department
    
    jobs = await JobPosting.find(query).sort("-created_at").to_list()

    # Attach candidate counts
    out = []
    for job in jobs:
        count = await Candidate.find(Candidate.job_id == job.id).count()
        out.append({**_ser_job(job), "candidate_count": count})
    return out


@router.post("/jobs", status_code=201)
async def create_job(
    body: JobCreate,
    current_user: dict = Depends(get_current_user),
):
    job = JobPosting(company_id=current_user["company_id"], **body.model_dump())
    await job.insert()
    return _ser_job(job)


@router.put("/jobs/{job_id}")
async def update_job(
    job_id: str,
    body: JobCreate,
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(job_id, current_user["company_id"])
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(job, k, v)
    await job.save()
    return _ser_job(job)


@router.put("/jobs/{job_id}/publish")
async def publish_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(job_id, current_user["company_id"])
    job.status = "open"
    job.posted_at = datetime.utcnow()
    await job.save()
    return {"message": "Job published", "status": "open"}


@router.put("/jobs/{job_id}/close")
async def close_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(job_id, current_user["company_id"])
    job.status = "closed"
    job.closed_at = datetime.utcnow()
    await job.save()
    return {"message": "Job closed"}


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    job = await _get_job(job_id, current_user["company_id"])
    await job.delete()


# ── Routes: Candidates ─────────────────────────────────────────
@router.get("/jobs/{job_id}/candidates")
async def list_candidates(
    job_id: str,
    stage: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {
        "job_id": UUID(job_id),
        "company_id": current_user["company_id"],
    }
    if stage: query["stage"] = stage
    
    candidates = await Candidate.find(query).sort("-created_at").to_list()
    return [_ser_candidate(c) for c in candidates]


@router.post("/jobs/{job_id}/candidates", status_code=201)
async def add_candidate(
    job_id: str,
    body: CandidateCreate,
    current_user: dict = Depends(get_current_user),
):
    await _get_job(job_id, current_user["company_id"])
    candidate = Candidate(
        job_id=UUID(job_id),
        company_id=current_user["company_id"],
        **body.model_dump(),
    )
    await candidate.insert()
    return _ser_candidate(candidate)


@router.put("/candidates/{candidate_id}/stage")
async def update_stage(
    candidate_id: str,
    body: StageUpdate,
    current_user: dict = Depends(get_current_user),
):
    if body.stage not in PIPELINE_STAGES:
        raise HTTPException(400, f"stage must be: {', '.join(PIPELINE_STAGES)}")
    
    c = await Candidate.find_one(
        Candidate.id == UUID(candidate_id),
        Candidate.company_id == current_user["company_id"],
    )
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
        job = await JobPosting.find_one(JobPosting.id == c.job_id)
        if job:
            job.filled_count = (job.filled_count or 0) + 1
            if job.filled_count >= job.headcount:
                job.status = "filled"
            await job.save()

    await c.save()
    return _ser_candidate(c)


@router.post("/candidates/{candidate_id}/notes", status_code=201)
async def add_note(
    candidate_id: str,
    body: NoteCreate,
    current_user: dict = Depends(get_current_user),
):
    note = HiringNote(
        candidate_id=UUID(candidate_id),
        company_id=current_user["company_id"],
        author_id=current_user["sub"],
        author_name=current_user.get("email", ""),
        **body.model_dump(),
    )
    await note.insert()
    return {"message": "Note added"}


@router.get("/candidates/{candidate_id}/notes")
async def get_notes(
    candidate_id: str,
    current_user: dict = Depends(get_current_user),
):
    notes = await HiringNote.find(
        HiringNote.candidate_id == UUID(candidate_id),
        HiringNote.company_id == current_user["company_id"]
    ).sort("-created_at").to_list()
    
    return [
        {"id": str(n.id), "author": n.author_name, "type": n.note_type,
         "content": n.content, "rating": n.rating, "created_at": str(n.created_at)}
        for n in notes
    ]


# ── Routes: Dashboard ──────────────────────────────────────────
@router.get("/ats/dashboard")
async def ats_dashboard(
    current_user: dict = Depends(get_current_user),
):
    """Hiring funnel stats."""
    company_id = current_user["company_id"]

    # Aggregate job stats
    pipeline_jobs = [
        {"$match": {"company_id": company_id}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "open": {"$sum": {"$cond": [{"$eq": ["$status", "open"]}, 1, 0]}},
                "filled": {"$sum": {"$cond": [{"$eq": ["$status", "filled"]}, 1, 0]}}
            }
        }
    ]
    jobs_res = await JobPosting.aggregate(pipeline_jobs).to_list()
    jobs_row = jobs_res[0] if jobs_res else {"total": 0, "open": 0, "filled": 0}

    # Aggregate candidate stage distribution
    pipeline_stages = [
        {"$match": {"company_id": company_id}},
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
    ]
    stage_res = await Candidate.aggregate(pipeline_stages).to_list()
    by_stage = {r["_id"]: r["count"] for r in stage_res}

    total_candidates = sum(by_stage.values())

    return {
        "jobs": {
            "total": jobs_row.get("total", 0),
            "open": jobs_row.get("open", 0),
            "filled": jobs_row.get("filled", 0),
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
async def _get_job(job_id, company_id):
    job = await JobPosting.find_one(JobPosting.id == UUID(job_id), JobPosting.company_id == UUID(company_id))
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
