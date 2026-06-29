"""Embed chunks with two vector types: dense (OpenAI) and sparse (BM25).

Dense vectors come from OpenAI ``text-embedding-3-small`` (1536-dim) via the
async client, batched and run concurrently. Sparse vectors come from fastembed's
``Qdrant/bm25`` model, which is synchronous and therefore executed in a thread
pool so it does not block the event loop.
"""

import asyncio
import logging
from dataclasses import dataclass

import openai
from fastembed import SparseTextEmbedding

from core.config import get_settings
from ingestion.schemas import Chunk

logger = logging.getLogger(__name__)


@dataclass
class EmbeddedChunk:
    """Dense + sparse embeddings for a single chunk, keyed by ``chunk_index``."""

    chunk_index: int
    dense_vector: list[float]  # 1536-dim
    sparse_indices: list[int]  # BM25 sparse indices
    sparse_values: list[float]  # BM25 sparse values


BATCH_SIZE = 100
_RATE_LIMIT_RETRY_DELAY_SECONDS = 10

_bm25_model: SparseTextEmbedding | None = None


def _get_bm25_model() -> SparseTextEmbedding:
    """Return a lazily-initialized, process-wide BM25 model singleton."""
    global _bm25_model
    if _bm25_model is None:
        _bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _bm25_model


def _compute_sparse(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """Compute BM25 sparse vectors for ``texts`` (runs in a thread executor)."""
    model = _get_bm25_model()
    results: list[tuple[list[int], list[float]]] = []
    for embedding in model.embed(texts):
        results.append(
            (embedding.indices.tolist(), embedding.values.tolist())
        )
    return results


async def _embed_dense_batch(
    client: openai.AsyncOpenAI, batch: list[str], model: str
) -> list[list[float]]:
    """Embed a single batch of texts, retrying once on rate limit."""
    try:
        response = await client.embeddings.create(input=batch, model=model)
    except openai.RateLimitError:
        logger.warning(
            "OpenAI rate limit hit; retrying batch of %d after %ds",
            len(batch),
            _RATE_LIMIT_RETRY_DELAY_SECONDS,
        )
        await asyncio.sleep(_RATE_LIMIT_RETRY_DELAY_SECONDS)
        response = await client.embeddings.create(input=batch, model=model)
    return [item.embedding for item in response.data]


async def embed_chunks(chunks: list[Chunk]) -> list[EmbeddedChunk]:
    """Embed all chunks (dense via OpenAI batched, sparse via fastembed).

    Returns :class:`EmbeddedChunk` objects in the same order as ``chunks``.
    """
    if not chunks:
        return []

    settings = get_settings()
    texts = [chunk.content for chunk in chunks]
    batches = [texts[i : i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]
    logger.info("Embedding %d chunks in %d batches", len(chunks), len(batches))

    loop = asyncio.get_running_loop()
    sparse_future = loop.run_in_executor(None, _compute_sparse, texts)

    dense_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    dense_batches = await asyncio.gather(
        *(
            _embed_dense_batch(dense_client, batch, settings.OPENAI_EMBEDDING_MODEL)
            for batch in batches
        )
    )
    dense_vectors = [vector for batch in dense_batches for vector in batch]
    sparse_vectors = await sparse_future

    return [
        EmbeddedChunk(
            chunk_index=chunk.chunk_index,
            dense_vector=dense_vectors[i],
            sparse_indices=sparse_vectors[i][0],
            sparse_values=sparse_vectors[i][1],
        )
        for i, chunk in enumerate(chunks)
    ]
