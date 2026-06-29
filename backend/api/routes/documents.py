"""Document listing and soft-delete endpoints.

``GET /api/documents`` lists non-archived documents (newest first) with optional
filters. ``DELETE /api/documents/{doc_id}`` soft-deletes a document by archiving
it in Postgres and flipping its Qdrant points' payload ``status`` to
``archived``; the underlying rows and points are retained for audit.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user
from core.access import UserScope, can_write_department, department_allowed, deny_access
from core.config import get_settings
from core.database import get_session
from core.qdrant import client as qdrant_client
from models.tables import AuditLog, Document

logger = logging.getLogger(__name__)

router = APIRouter()

_VISIBLE_STATUSES = ("active", "processing", "failed")


@router.get("/documents")
async def list_documents(
    doc_type: str | None = Query(None),
    department: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    scope: UserScope = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List non-archived documents the caller may see, newest first.

    Non-admins see documents in their departments plus shared (null-department)
    docs. A client ``department`` filter narrows within that scope; an
    out-of-scope value is rejected (403).
    """
    if not department_allowed(scope, department):
        await deny_access(db, scope, department, "documents:list")

    stmt = select(Document).where(Document.status.in_(_VISIBLE_STATUSES))
    if not scope.is_admin:
        stmt = stmt.where(
            or_(
                Document.department.in_(scope.departments),
                Document.department.is_(None),
            )
        )
    if doc_type is not None:
        stmt = stmt.where(Document.doc_type == doc_type)
    if department is not None:
        stmt = stmt.where(Document.department == department)
    stmt = stmt.order_by(Document.upload_date.desc()).limit(limit)

    documents = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(doc.id),
            "filename": doc.original_filename,
            "doc_type": doc.doc_type,
            "department": doc.department,
            "status": doc.status,
            "version": doc.version,
            "page_count": doc.page_count,
            "file_size_bytes": doc.file_size_bytes,
            "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
        }
        for doc in documents
    ]


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: UUID,
    scope: UserScope = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """Soft-delete a document: archive it in Postgres and Qdrant.

    Non-admins may only delete documents within their own departments (not
    shared docs and not other departments').
    """
    existing = await db.get(Document, doc_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    if not can_write_department(scope, existing.department):
        await deny_access(db, scope, existing.department, "documents:delete")

    await db.execute(
        update(Document).where(Document.id == doc_id).values(status="archived")
    )
    await qdrant_client.set_payload(
        collection_name=get_settings().QDRANT_COLLECTION,
        payload={"status": "archived"},
        points=Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=str(doc_id)))
            ]
        ),
    )
    db.add(
        AuditLog(
            event_type="doc_deleted",
            entity_id=doc_id,
            details={"deleted_by": str(scope.id)},
        )
    )
    await db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
