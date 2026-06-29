"""Tests for query embedding with OpenAI and BM25 fully mocked."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import retrieval.query_embedder as qe
from retrieval.query_embedder import embed_query


@pytest.fixture
def patched_embedder(monkeypatch):
    """Patch the dense OpenAI client + BM25 sparse computation.

    Returns ``(dense_create_mock, sparse_mock)`` so tests can assert call counts.
    """
    qe._dense_client = None  # reset singleton between tests

    create_mock = AsyncMock(
        return_value=MagicMock(data=[MagicMock(embedding=[0.1] * 1536)])
    )
    fake_client = MagicMock()
    fake_client.embeddings.create = create_mock
    monkeypatch.setattr(
        "retrieval.query_embedder.openai.AsyncOpenAI", lambda **kwargs: fake_client
    )

    sparse_mock = MagicMock(return_value=[([1, 2], [0.5, 0.3])])
    monkeypatch.setattr("retrieval.query_embedder._compute_sparse", sparse_mock)

    return create_mock, sparse_mock


@pytest.mark.asyncio
async def test_returns_dense_and_sparse_tuple(patched_embedder):
    dense, indices, values = await embed_query("what is the vacation policy?")

    assert isinstance(dense, list) and len(dense) == 1536
    assert all(isinstance(x, float) for x in dense)
    assert indices == [1, 2]
    assert values == [0.5, 0.3]
    assert all(isinstance(i, int) for i in indices)
    assert all(isinstance(v, float) for v in values)


@pytest.mark.asyncio
async def test_dense_and_sparse_each_run_once(patched_embedder):
    create_mock, sparse_mock = patched_embedder
    await embed_query("password reset steps")

    create_mock.assert_called_once()
    sparse_mock.assert_called_once_with(["password reset steps"])


@pytest.mark.asyncio
async def test_dense_client_is_a_reused_singleton(patched_embedder):
    await embed_query("first query")
    first = qe._dense_client
    await embed_query("second query")
    assert qe._dense_client is first
