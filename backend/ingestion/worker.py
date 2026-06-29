"""Celery app and the async document ingestion task.

The task body is asynchronous (embedding, Qdrant, Postgres, Redis are all
async), but Celery tasks are synchronous. We therefore drive the coroutine on a
single persistent event loop owned by the worker process via :func:`_run`. A
persistent loop (rather than :func:`asyncio.run` per call) keeps the
process-wide async clients in :mod:`core.qdrant` and :mod:`core.redis_client`
bound to one loop across successive tasks.

Ordering guarantees:
- The uploaded temp file is deleted only *after* a successful commit, so a
  failure never loses the source file.
- Qdrant upserts use ``wait=True`` (see :mod:`ingestion.indexer`).
- The task is idempotent: a re-run for the same ``document_id`` first clears any
  partially-indexed points/rows, then re-indexes cleanly.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Coroutine, TypeVar
from uuid import UUID

from celery import Celery
from celery.signals import worker_process_init
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
)
from sqlalchemy import delete, update

from core.config import get_settings
from core.database import async_session_factory
from core.qdrant import client as qdrant_client
from core.redis_client import client as redis_client
from ingestion.dispatcher import parse_and_chunk
from ingestion.embedder import embed_chunks
from ingestion.indexer import index_chunks
from ingestion.versioning import archive_existing
from models.tables import AuditLog, Document, DocumentChunk

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "rag_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
)

JOB_TTL_SECONDS = 3600

_T = TypeVar("_T")
# Initialised post-fork by _init_worker_loop; None in the parent process.
_loop: asyncio.AbstractEventLoop | None = None


@worker_process_init.connect
def _init_worker_loop(**kwargs: Any) -> None:
    """Create a fresh event loop in each worker process after prefork().

    Module-level asyncio.new_event_loop() runs in the parent before fork(),
    and the loop's internal file descriptors are inherited by every child on
    CPython 3.12+, causing "Event loop is closed" / selector errors. Deferring
    creation to this signal guarantees each worker owns an unshared loop.
    """
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    """Run ``coro`` to completion on the worker's persistent event loop."""
    return _loop.run_until_complete(coro)  # type: ignore[union-attr]


async def _set_job(task_id: str, data: dict) -> None:
    """Write the pollable job record to Redis with a 1-hour TTL."""
    await redis_client.set(f"job:{task_id}", json.dumps(data), ex=JOB_TTL_SECONDS)


async def _reset_index(document_id: UUID) -> None:
    """Drop any previously-indexed points/rows for ``document_id`` (idempotency)."""
    await qdrant_client.delete(
        collection_name=settings.QDRANT_COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=str(document_id)),
                    )
                ]
            )
        ),
        wait=True,
    )


async def _ingest(task_id: str, document_id: str, file_path: str, metadata: dict) -> dict:
    doc_uuid = UUID(document_id)
    original_filename = metadata["original_filename"]

    await _set_job(task_id, {"status": "parsing", "document_id": document_id})
    parsed, chunks = parse_and_chunk(Path(file_path), metadata)

    await _set_job(task_id, {"status": "embedding", "document_id": document_id})
    embedded = await embed_chunks(chunks)

    await _set_job(task_id, {"status": "indexing", "document_id": document_id})
    async with async_session_factory() as db:
        # Idempotency: clear partial state from any prior run before re-indexing.
        await _reset_index(doc_uuid)
        await db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == doc_uuid)
        )

        archive = await archive_existing(original_filename, db)
        new_version = archive.old_version + 1 if archive else 1
        replaced = str(archive.old_document_id) if archive else None

        doc_payload = {
            "doc_type": metadata["doc_type"],
            "department": metadata.get("department"),
            "filename": parsed.filename,
            "upload_date": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }
        await index_chunks(doc_uuid, chunks, embedded, doc_payload, db)

        await db.execute(
            update(Document)
            .where(Document.id == doc_uuid)
            .values(status="active", page_count=parsed.page_count, version=new_version)
        )
        db.add(
            AuditLog(
                event_type="doc_uploaded",
                entity_id=doc_uuid,
                details={
                    "filename": original_filename,
                    "chunks": len(chunks),
                    "replaced": replaced,
                },
            )
        )
        await db.commit()

    result = {
        "status": "complete",
        "document_id": document_id,
        "chunk_count": len(chunks),
    }
    await _set_job(task_id, result)
    # Only now is it safe to remove the source file.
    Path(file_path).unlink(missing_ok=True)
    return result


async def _mark_failed(task_id: str, document_id: str, error: str) -> None:
    await _set_job(
        task_id, {"status": "failed", "document_id": document_id, "error": error}
    )
    async with async_session_factory() as db:
        await db.execute(
            update(Document)
            .where(Document.id == UUID(document_id))
            .values(status="failed")
        )
        await db.commit()


@celery_app.task(bind=True, name="ingest.ingest_document", max_retries=2)
def ingest_document(self, document_id: str, file_path: str, metadata: dict) -> dict:
    """Parse, embed, index, and finalize a single uploaded document."""
    task_id = self.request.id
    logger.info("Starting ingestion task %s for document %s", task_id, document_id)
    try:
        return _run(_ingest(task_id, document_id, file_path, metadata))
    except Exception as exc:  # noqa: BLE001 - surface to Redis/DB then retry
        logger.exception("Ingestion task %s failed for document %s", task_id, document_id)
        _run(_mark_failed(task_id, document_id, str(exc)))
        raise self.retry(exc=exc)
