"""FlashRank cross-encoder reranking of hybrid-search candidates.

FlashRank is synchronous, so reranking runs in a thread executor. The ``Ranker``
is a process-wide singleton (the model is loaded once, not per call). Scores are
already normalized to 0.0–1.0 (higher = more relevant).
"""

import asyncio
import logging

from flashrank import Ranker, RerankRequest

logger = logging.getLogger(__name__)

_RANKER_MODEL = "ms-marco-MiniLM-L-12-v2"
_RANKER_CACHE_DIR = "/tmp/flashrank"  # Linux/Docker path; tests mock the Ranker

_ranker: Ranker | None = None


def _get_ranker() -> Ranker:
    """Return a lazily-initialized, process-wide FlashRank ranker singleton."""
    global _ranker
    if _ranker is None:
        _ranker = Ranker(model_name=_RANKER_MODEL, cache_dir=_RANKER_CACHE_DIR)
    return _ranker


def _rerank_sync(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Rerank ``candidates`` against ``query`` and return the top ``top_k`` (sync)."""
    passages = [
        {"id": i, "text": candidate["content"]}
        for i, candidate in enumerate(candidates)
    ]
    request = RerankRequest(query=query, passages=passages)
    ranked = _get_ranker().rerank(request)

    enriched = [
        {**candidates[item["id"]], "score": float(item["score"])} for item in ranked
    ]
    enriched.sort(key=lambda c: c["score"], reverse=True)
    return enriched[:top_k]


async def rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Rerank ``candidates`` with FlashRank, returning the top ``top_k``.

    Each returned dict is the original candidate enriched with a ``score`` float
    (0.0–1.0), sorted by score descending. Returns ``[]`` for no candidates.
    """
    if not candidates:
        return []

    loop = asyncio.get_running_loop()
    reranked = await loop.run_in_executor(
        None, _rerank_sync, query, candidates, top_k
    )
    best = reranked[0]["score"] if reranked else 0.0
    logger.info(
        "Reranked %d candidates → top %d (best score: %.3f)",
        len(candidates),
        len(reranked),
        best,
    )
    return reranked
