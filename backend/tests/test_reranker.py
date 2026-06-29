"""Tests for the FlashRank reranker with the Ranker mocked."""

from unittest.mock import MagicMock

import pytest

from retrieval.reranker import rerank


class _FakeRanker:
    """Assigns higher scores to later passages — i.e. reverses input order."""

    def rerank(self, request):
        n = len(request.passages)
        return [
            {"id": p["id"], "score": (p["id"] + 1) / n} for p in request.passages
        ]


def _candidates(n: int) -> list[dict]:
    return [
        {"content": f"passage {i}", "chunk_index": i, "document_id": "doc"}
        for i in range(n)
    ]


@pytest.fixture
def patched_ranker(monkeypatch):
    monkeypatch.setattr(
        "retrieval.reranker._get_ranker", MagicMock(return_value=_FakeRanker())
    )


@pytest.mark.asyncio
async def test_returns_top_k_sorted_by_score_desc(patched_ranker):
    result = await rerank("vacation policy", _candidates(3), top_k=2)

    assert len(result) == 2
    assert all(isinstance(c["score"], float) for c in result)
    scores = [c["score"] for c in result]
    assert scores == sorted(scores, reverse=True)
    # Input order reversed: passage 2 (highest score) ranks first.
    assert result[0]["content"] == "passage 2"


@pytest.mark.asyncio
async def test_preserves_original_candidate_fields(patched_ranker):
    result = await rerank("q", _candidates(3), top_k=3)
    for c in result:
        assert "chunk_index" in c
        assert c["document_id"] == "doc"


@pytest.mark.asyncio
async def test_empty_candidates_returns_empty(patched_ranker):
    assert await rerank("q", [], top_k=5) == []
