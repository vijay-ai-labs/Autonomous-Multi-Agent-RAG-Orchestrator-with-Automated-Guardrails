"""Ingestion endpoints: upload a document and poll its processing job.

``POST /api/ingest`` validates and persists the upload, records a ``processing``
document row, and enqueues the Celery ingestion task. ``GET /api/ingest/{job_id}
/status`` reads the job record the worker maintains in Redis. Stored file paths
are never returned to clients.
"""

import json
import logging
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user, get_current_user_id
from core.access import UserScope, can_write_department, deny_access
from core.config import get_settings
from core.database import get_session
from core.redis_client import client as redis_client
from ingestion.worker import ingest_document
from models.tables import Document

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm"}
ALLOWED_DOC_TYPES = {"policy", "hr", "it", "sop", "compliance", "faq"}

UPLOAD_DIR = Path(tempfile.gettempdir()) / "rag_uploads"


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    department: str | None = Form(None),
    scope: UserScope = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Accept a document upload and enqueue it for async ingestion.

    Non-admins may only upload into a department they belong to; only admins
    may create shared (no-department) documents.
    """
    if not can_write_department(scope, department):
        await deny_access(db, scope, department, "ingest")

    settings = get_settings()
    original_filename = file.filename or ""
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{extension}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid doc_type '{doc_type}'. Allowed: {sorted(ALLOWED_DOC_TYPES)}",
        )

    contents = await file.read()
    size_bytes = len(contents)
    if size_bytes > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4()}_{original_filename}"
    tmp_path = UPLOAD_DIR / stored_filename
    tmp_path.write_bytes(contents)

    document = Document(
        filename=stored_filename,
        original_filename=original_filename,
        doc_type=doc_type,
        department=department,
        status="processing",
        version=1,
        uploader_id=scope.id,
        file_size_bytes=size_bytes,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    metadata = {
        "filename": stored_filename,
        "original_filename": original_filename,
        "doc_type": doc_type,
        "department": department,
        "file_size_bytes": size_bytes,
    }
    task = ingest_document.delay(str(document.id), str(tmp_path), metadata)
    logger.info("Enqueued ingestion task %s for document %s", task.id, document.id)

    return {
        "job_id": task.id,
        "document_id": str(document.id),
        "status": "processing",
        "filename": original_filename,
    }


@router.get("/ingest/{job_id}/status")
async def ingest_status(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
) -> dict:
    """Return the current Redis-tracked status for an ingestion job."""
    raw = await redis_client.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    record = json.loads(raw)
    return {
        "job_id": job_id,
        "status": record.get("status"),
        "document_id": record.get("document_id"),
        "chunk_count": record.get("chunk_count"),
        "error": record.get("error"),
    }
