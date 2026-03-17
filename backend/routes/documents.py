import uuid
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from models import EmployeeDocument
from utils.auth import get_current_user
from uuid import UUID

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


@router.get("/employees/{employee_id}")
async def list_documents(
    employee_id: str,
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    query = {
        "employee_id": UUID(employee_id),
        "company_id": current_user["company_id"],
        "is_active": True,
    }
    if category:
        query["category"] = category
        
    docs = await EmployeeDocument.find(query).sort("-created_at").to_list()
    return [_serialize(d) for d in docs]


@router.post("/employees/{employee_id}", status_code=201)
async def upload_document(
    employee_id: str,
    category: str = "other",
    description: str = "",
    file: UploadFile = File(...),
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
    doc_id = uuid.uuid4()
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
        employee_id=UUID(employee_id),
        company_id=current_user["company_id"],
        category=category,
        original_filename=file.filename or "document",
        stored_filename=stored_name,
        mime_type=mime,
        file_size_bytes=len(content),
        description=description,
        uploaded_by=current_user.get("email", ""),
    )
    await doc.insert()
    return _serialize(doc)


@router.get("/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    doc = await EmployeeDocument.find_one(
        EmployeeDocument.id == UUID(doc_id),
        EmployeeDocument.company_id == current_user["company_id"],
        EmployeeDocument.is_active == True,
    )
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
    current_user: dict = Depends(get_current_user),
):
    doc = await EmployeeDocument.find_one(
        EmployeeDocument.id == UUID(doc_id),
        EmployeeDocument.company_id == current_user["company_id"],
    )
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.is_active = False
    await doc.save()


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
