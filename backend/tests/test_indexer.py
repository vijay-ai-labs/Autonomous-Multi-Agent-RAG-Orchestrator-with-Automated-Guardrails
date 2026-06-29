"""Tests for index_chunks: Qdrant upsert shape + Postgres row insertion."""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

import ingestion.indexer as indexer
from ingestion.embedder import EmbeddedChunk
from ingestion.schemas import Chunk
from tests.conftest import FakeAsyncSession


def _chunks(n: int) -> list[Chunk]:
    return [
        Chunk(
            chunk_index=i,
            content=f"chunk text {i}",
            page_number=i + 1,
            section=f"sec-{i}",
            char_count=len(f"chunk text {i}"),
            token_count=3,
        )
        for i in range(n)
    ]


def _embedded(n: int) -> list[EmbeddedChunk]:
    return [
        EmbeddedChunk(
            chunk_index=i,
            dense_vector=[0.1] * 1536,
            sparse_indices=[1, 2, 3],
            sparse_values=[0.5, 0.3, 0.2],
        )
        for i in range(n)
    ]


@pytest.fixture
def doc_payload() -> dict:
    return {
        "doc_type": "policy",
        "department": "hr",
        "filename": "stored.pdf",
        "upload_date": "2026-06-14T00:00:00+00:00",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_index_chunks_upsert_and_rows(monkeypatch, doc_payload):
    mock_client = MagicMock()
    mock_client.upsert = AsyncMock()
    monkeypatch.setattr(indexer, "client", mock_client)

    db = FakeAsyncSession()
    document_id = uuid4()
    chunks = _chunks(3)
    embedded = _embedded(3)

    point_ids = await indexer.index_chunks(
        document_id, chunks, embedded, doc_payload, db
    )

    # Returns one UUID per chunk, in order.
    assert len(point_ids) == 3
    assert all(isinstance(pid, UUID) for pid in point_ids)

    # Upsert called against the configured collection.
    kwargs = mock_client.upsert.call_args.kwargs
    assert kwargs["collection_name"] == "company_docs"
    assert kwargs["wait"] is True

    points = kwargs["points"]
    assert len(points) == 3
    # Each point carries both the dense (default "") and sparse "bm25" vectors.
    for point in points:
        assert "bm25" in point.vector
        assert "" in point.vector

    payload0 = points[0].payload
    assert payload0["content"] == "chunk text 0"
    assert payload0["document_id"] == str(document_id)
    assert payload0["chunk_index"] == 0
    assert payload0["status"] == "active"

    # One DocumentChunk row per chunk, linked to its point id.
    assert len(db.added) == 3
    assert db.added[0].qdrant_point_id == point_ids[0]
    assert db.added[0].char_count == chunks[0].char_count
