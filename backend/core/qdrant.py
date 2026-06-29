"""Qdrant client initialization and idempotent collection setup.

The ``company_docs`` collection holds dense 1536-dim embeddings plus a named
sparse vector (``bm25``) for hybrid search. Payload indexes are created for the
metadata fields used in retrieval filtering.
"""

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)

from core.config import get_settings

logger = logging.getLogger(__name__)

VECTOR_SIZE = 1536
SPARSE_VECTOR_NAME = "bm25"

# Payload field -> index schema type
_PAYLOAD_INDEXES: dict[str, PayloadSchemaType] = {
    "doc_type": PayloadSchemaType.KEYWORD,
    "department": PayloadSchemaType.KEYWORD,
    "status": PayloadSchemaType.KEYWORD,
    "document_id": PayloadSchemaType.KEYWORD,
    "upload_date": PayloadSchemaType.DATETIME,
}

_settings = get_settings()

client = AsyncQdrantClient(url=_settings.QDRANT_URL)


async def ensure_collection() -> None:
    """Create the collection and payload indexes if they do not already exist.

    Never drops or recreates an existing collection.
    """
    collection_name = _settings.QDRANT_COLLECTION

    if await client.collection_exists(collection_name):
        logger.info("Qdrant collection '%s' already exists; skipping create", collection_name)
        return

    logger.info("Creating Qdrant collection '%s'", collection_name)
    await client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
    )

    for field_name, schema_type in _PAYLOAD_INDEXES.items():
        await client.create_payload_index(
            collection_name=collection_name,
            field_name=field_name,
            field_schema=schema_type,
        )
        logger.info("Created payload index on '%s' (%s)", field_name, schema_type)


async def check_qdrant() -> bool:
    """Return ``True`` if Qdrant is reachable."""
    await client.get_collections()
    return True


async def close_qdrant() -> None:
    """Close the underlying Qdrant client."""
    await client.close()
