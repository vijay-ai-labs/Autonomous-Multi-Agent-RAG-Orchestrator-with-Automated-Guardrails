"""Tests for the dense+sparse embedder with OpenAI and BM25 fully mocked."""

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingestion.embedder import BATCH_SIZE, embed_chunks
from ingestion.schemas import Chunk


def _make_chunks(n: int) -> list[Chunk]:
    return [
        Chunk(
            chunk_index=i,
            content=f"chunk text {i}",
            page_number=1,
            section=None,
            char_count=len(f"chunk text {i}"),
            token_count=3,
        )
        for i in range(n)
    ]


def _fake_openai_client() -> MagicMock:
    def create(input, model):  # noqa: A002 - mirrors OpenAI kwarg name
        data = [MagicMock(embedding=[0.1] * 1536) for _ in input]
        return MagicMock(data=data)

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=create)
    return client


@pytest.fixture
def patched_embedder(monkeypatch):
    """Patch OpenAI client + BM25 sparse computation; return the mock client."""
    client = _fake_openai_client()
    monkeypatch.setattr(
        "ingestion.embedder.openai.AsyncOpenAI", lambda **kwargs: client
    )
    monkeypatch.setattr(
        "ingestion.embedder._compute_sparse",
        lambda texts: [([1, 5, 9], [0.7, 0.2, 0.1]) for _ in texts],
    )
    return client


@pytest.mark.asyncio
async def test_returns_one_embedded_chunk_per_input(patched_embedder):
    chunks = _make_chunks(5)
    result = await embed_chunks(chunks)
    assert len(result) == len(chunks)
    assert [e.chunk_index for e in result] == [c.chunk_index for c in chunks]


@pytest.mark.asyncio
async def test_dense_vectors_are_1536_dim(patched_embedder):
    result = await embed_chunks(_make_chunks(3))
    assert all(len(e.dense_vector) == 1536 for e in result)


@pytest.mark.asyncio
async def test_batches_into_ceil_n_over_batch_size(patched_embedder):
    n = 2 * BATCH_SIZE + 7  # 207 -> 3 batches
    await embed_chunks(_make_chunks(n))
    assert patched_embedder.embeddings.create.call_count == math.ceil(n / BATCH_SIZE)


@pytest.mark.asyncio
async def test_sparse_indices_and_values_types(patched_embedder):
    result = await embed_chunks(_make_chunks(2))
    for e in result:
        assert isinstance(e.sparse_indices, list)
        assert isinstance(e.sparse_values, list)
        assert all(isinstance(i, int) for i in e.sparse_indices)
        assert all(isinstance(v, float) for v in e.sparse_values)


@pytest.mark.asyncio
async def test_empty_input_returns_empty(patched_embedder):
    assert await embed_chunks([]) == []
