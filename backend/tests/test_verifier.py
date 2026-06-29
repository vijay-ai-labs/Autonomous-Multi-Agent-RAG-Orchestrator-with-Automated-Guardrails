"""Tests for the pure-sync evidence verifier (no mocks needed)."""

from retrieval.schemas import RetrievalResult, RetrievedChunk
from retrieval.verifier import verify_evidence


def _chunk(score: float, idx: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_index=idx,
        content=f"content {idx}",
        page_number=1,
        section=None,
        filename="handbook.pdf",
        doc_type="policy",
        department="hr",
        document_id="doc-123",
        score=score,
        search_score=0.5,
    )


def _result(scores: list[float]) -> RetrievalResult:
    chunks = [_chunk(s, i) for i, s in enumerate(scores)]
    return RetrievalResult(query="q", chunks=chunks, total_candidates=len(chunks))


def test_no_chunks_fails():
    result = verify_evidence(_result([]))
    assert result.passed is False
    assert "No relevant documents" in result.reason
    assert result.top_score == 0.0


def test_single_chunk_fails_insufficient_evidence():
    result = verify_evidence(_result([0.9]))
    assert result.passed is False
    assert "Insufficient evidence" in result.reason
    assert result.top_score == 0.9


def test_low_scores_fail_not_relevant_enough():
    result = verify_evidence(_result([0.3, 0.3]))
    assert result.passed is False
    assert "not relevant enough" in result.reason


def test_sufficient_evidence_passes():
    result = verify_evidence(_result([0.7, 0.65]))
    assert result.passed is True
    assert result.reason == "Evidence sufficient."


def test_top_score_matches_first_chunk():
    res = _result([0.82, 0.4])
    result = verify_evidence(res)
    assert result.top_score == res.chunks[0].score
