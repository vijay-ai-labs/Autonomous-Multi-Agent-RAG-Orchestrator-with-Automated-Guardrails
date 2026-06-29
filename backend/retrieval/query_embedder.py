"""Embed a single query string into dense + sparse vectors.

Mirrors the indexing-time embedding so query and document vectors share a space:
dense via OpenAI ``text-embedding-3-small`` (1536-dim), sparse via the fastembed
``Qdrant/bm25`` model reused from :mod:`ingestion.embedder`. The BM25 model is the
same process-wide singleton used during indexing — no second instance is created.

Unlike :func:`ingestion.embedder.embed_chunks` (which builds a per-call OpenAI
client for batched indexing), this module keeps its own lazily-initialized
``AsyncOpenAI`` singleton, since one is needed per process for query-time embedding
and none is exposed for import from the embedder.
"""

import asyncio
import logging

import openai

from core.config import get_settings
from ingestion.embedder import _compute_sparse

logger = logging.getLogger(__name__)

_dense_client: openai.AsyncOpenAI | None = None


def _get_dense_client() -> openai.AsyncOpenAI:
    """Return a lazily-initialized, process-wide OpenAI async client singleton."""
    global _dense_client
    if _dense_client is None:
        _dense_client = openai.AsyncOpenAI(api_key=get_settings().OPENAI_API_KEY)
    return _dense_client


async def _embed_dense(query_text: str) -> list[float]:
    """Embed ``query_text`` into a 1536-dim dense vector via OpenAI."""
    settings = get_settings()
    response = await _get_dense_client().embeddings.create(
        input=query_text, model=settings.OPENAI_EMBEDDING_MODEL
    )
    return response.data[0].embedding


async def _embed_sparse(query_text: str) -> tuple[list[int], list[float]]:
    """Embed ``query_text`` into BM25 sparse (indices, values) in a thread executor."""
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, _compute_sparse, [query_text])
    return results[0]


async def embed_query(query_text: str) -> tuple[list[float], list[int], list[float]]:
    """Embed a single query string into dense + sparse vectors.

    Dense and sparse embeddings run concurrently.

    Returns:
        ``(dense_vector, sparse_indices, sparse_values)``.
    """
    dense_vector, (sparse_indices, sparse_values) = await asyncio.gather(
        _embed_dense(query_text),
        _embed_sparse(query_text),
    )
    logger.info(
        "Query embedded: dense=%d-dim, sparse=%d terms",
        len(dense_vector),
        len(sparse_indices),
    )
    return dense_vector, sparse_indices, sparse_values
