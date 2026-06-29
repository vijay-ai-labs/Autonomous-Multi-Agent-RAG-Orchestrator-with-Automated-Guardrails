"""Index embedded chunks into Qdrant (hybrid vectors) and Postgres.

For each chunk a new Qdrant point UUID is minted; that same UUID is stored on
the corresponding ``document_chunks`` row as ``qdrant_point_id`` so the two
stores stay linked. The dense vector is stored under the default unnamed vector
(``""``) and the sparse BM25 vector under the named ``bm25`` slot, matching the
collection created in :mod:`core.qdrant`.
"""

import logging
from uuid import UUID, uuid4

from qdrant_client.http.models import PointStruct, SparseVector
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.qdrant import client
from models.tables import DocumentChunk
from ingestion.embedder import EmbeddedChunk
from ingestion.schemas import Chunk

logger = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 100


async def index_chunks(
    document_id: UUID,
    chunks: list[Chunk],
    embedded: list[EmbeddedChunk],
    doc_payload: dict,
    db: AsyncSession,
) -> list[UUID]:
    """Upsert chunks to Qdrant and insert ``document_chunks`` rows.

    ``doc_payload`` carries the document-level metadata copied onto every point:
    ``doc_type``, ``department``, ``filename``, ``upload_date``, ``status``.
    Returns the minted Qdrant point ids in chunk order. Flushes (no commit) so
    the caller controls the transaction boundary.
    """
    collection = get_settings().QDRANT_COLLECTION
    point_ids: list[UUID] = [uuid4() for _ in chunks]
    points: list[PointStruct] = []
    rows: list[DocumentChunk] = []

    for chunk, embed, point_id in zip(chunks, embedded, point_ids):
        payload = {
            "document_id": str(document_id),
            "chunk_id": str(point_id),
            "doc_type": doc_payload["doc_type"],
            "department": doc_payload.get("department"),
            "filename": doc_payload["filename"],
            "page_number": chunk.page_number,
            "section": chunk.section,
            "upload_date": doc_payload["upload_date"],
            "status": "active",
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
        }
        points.append(
            PointStruct(
                id=str(point_id),
                vector={
                    "": embed.dense_vector,
                    "bm25": SparseVector(
                        indices=embed.sparse_indices,
                        values=embed.sparse_values,
                    ),
                },
                payload=payload,
            )
        )
        rows.append(
            DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                page_number=chunk.page_number,
                section=chunk.section,
                char_count=chunk.char_count,
                qdrant_point_id=point_id,
            )
        )

    for start in range(0, len(points), UPSERT_BATCH_SIZE):
        batch = points[start : start + UPSERT_BATCH_SIZE]
        await client.upsert(collection_name=collection, points=batch, wait=True)

    db.add_all(rows)
    await db.flush()

    logger.info(
        "Indexed %d chunks for document %s into Qdrant + Postgres",
        len(chunks),
        document_id,
    )
    return point_ids
