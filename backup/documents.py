"""
Employee document storage.
Upload, list, and download documents attached to employees.
Stores files on local disk (configure S3 in production via DOC_STORAGE=s3).

POST   /documents/employees/{id}    upload document
GET    /documents/employees/{id}    list documents
GET    /documents/{doc_id}          download document
DELETE /documents/{doc_id}          delete document
"""
import uuid
import os
import shutil
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, Text, select
from sqlalchemy.dialects.postgresql import UUID
from database import Base, get_db
from utils.auth import get_current_user

router = APIRouter(prefix="/documents", tags=["documents"])

DOC_DIR = os.getenv("DOC_STORAGE_PATH", "./documents")
MAX_FILE_SIZE_MB = 10
ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
}

DOCUMENT_CATEGORIES = [
    "i9",
    "w4",
    "offer_letter",
    "employment_agreement",
    "background_check",
    "benefits_enrollment",
    "direct_deposit",
    "performance_review",
    "disciplinary",
    "other",
]


class EmployeeDocument(Base):
    __tablename__ = "employee_documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"))
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"))
    category = Column(String(50), default="other")
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100))
    file_size_bytes = Column(Integer, default=0)
    description = Column(Text)
    uploaded_by = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


@router.get("/employees/{employee_id}")
async def list_documents(
    employee_id: str,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    q = select(EmployeeDocument).where(
        EmployeeDocument.employee_id == employee_id,
        EmployeeDocument.company_id == current_user["company_id"],
        EmployeeDocument.is_active == True,
    )
    if category:
        q = q.where(EmployeeDocument.category == category)
    q = q.order_by(EmployeeDocument.created_at.desc())
    result = await db.execute(q)
    docs = result.scalars().all()
    return [_serialize(d) for d in docs]


@router.post("/employees/{employee_id}", status_code=201)
async def upload_document(
    employee_id: str,
    category: str = "other",
    description: str = "",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if category not in DOCUMENT_CATEGORIES:
        raise HTTPException(400, f"Category must be one of: {', '.join(DOCUMENT_CATEGORIES)}")

    # Validate file type
    mime = file.content_type or ""
    if mime not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type not allowed. Accepted: PDF, JPG, PNG, DOC, DOCX, TXT")

    # Read and check size
    content = await file.read()
    size_mb = len(content) / 1024 / 1024
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(400, f"File too large. Max: {MAX_FILE_SIZE_MB}MB")

    # Store file
    doc_id = str(uuid.uuid4())
    ext = ALLOWED_TYPES[mime]
    stored_name = f"{doc_id}{ext}"
    emp_dir = os.path.join(DOC_DIR, str(current_user["company_id"]), employee_id)
    os.makedirs(emp_dir, exist_ok=True)
    file_path = os.path.join(emp_dir, stored_name)

    with open(file_path, "wb") as f:
        f.write(content)

    # Save metadata
    doc = EmployeeDocument(
        id=doc_id,
        employee_id=employee_id,
        company_id=current_user["company_id"],
        category=category,
        original_filename=file.filename or "document",
        stored_filename=stored_name,
        mime_type=mime,
        file_size_bytes=len(content),
        description=description,
        uploaded_by=current_user.get("email", ""),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return _serialize(doc)


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.company_id == current_user["company_id"],
            EmployeeDocument.is_active == True,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    file_path = os.path.join(
        DOC_DIR, str(doc.company_id), str(doc.employee_id), doc.stored_filename
    )
    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found on disk")

    return FileResponse(
        file_path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.original_filename,
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(EmployeeDocument).where(
            EmployeeDocument.id == doc_id,
            EmployeeDocument.company_id == current_user["company_id"],
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.is_active = False
    await db.commit()


def _serialize(d: EmployeeDocument) -> dict:
    return {
        "id": str(d.id),
        "employee_id": str(d.employee_id),
        "category": d.category,
        "original_filename": d.original_filename,
        "mime_type": d.mime_type,
        "file_size_bytes": d.file_size_bytes,
        "file_size_display": f"{d.file_size_bytes / 1024:.1f} KB" if d.file_size_bytes else "0 KB",
        "description": d.description,
        "uploaded_by": d.uploaded_by,
        "download_url": f"/documents/{d.id}/download",
        "created_at": str(d.created_at),
    }
