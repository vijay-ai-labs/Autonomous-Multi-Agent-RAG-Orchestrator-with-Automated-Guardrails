"""Soft-replace versioning for re-uploaded documents.

When a file with the same ``original_filename`` is uploaded again, the prior
active document is archived in both stores (Postgres ``status='archived'`` and a
Qdrant payload update over all of its points) rather than deleted, preserving an
audit trail. The new document then takes ``version = old_version + 1``.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.qdrant import client
from models.tables import Document

logger = logging.getLogger(__name__)


@dataclass
class ArchiveResult:
    """Outcome of archiving a prior active document version."""

    old_document_id: UUID
    old_version: int


async def archive_existing(
    original_filename: str,
    db: AsyncSession,
) -> ArchiveResult | None:
    """Archive the currently active document for ``original_filename``, if any.

    Sets Postgres ``status='archived'`` and flips every matching Qdrant point's
    payload ``status`` to ``archived``. Returns the archived document's id and
    version (so the caller can set the new version), or ``None`` if there was no
    active document to replace.
    """
    result = await db.execute(
        select(Document.id, Document.version)
        .where(
            Document.original_filename == original_filename,
            Document.status == "active",
        )
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None

    old_id, old_version = row

    await db.execute(
        update(Document).where(Document.id == old_id).values(status="archived")
    )

    await client.set_payload(
        collection_name=get_settings().QDRANT_COLLECTION,
        payload={"status": "archived"},
        points=Filter(
            must=[
                FieldCondition(
                    key="document_id", match=MatchValue(value=str(old_id))
                )
            ]
        ),
    )

    logger.info("Archived existing document %s for %s", old_id, original_filename)
    return ArchiveResult(old_document_id=old_id, old_version=old_version)
