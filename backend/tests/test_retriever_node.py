"""Tests for the async Retriever node (retrieve() mocked)."""

import pytest

from agents.retriever import retriever_node
from agents.state import AgentState
from retrieval.schemas import RetrievalResult, RetrievedChunk, VerificationResult


def _state(**kwargs) -> AgentState:
    base = {
        "query": "vacation policy?", "query_id": "abc", "route": "retrieve",
        "route_reason": None, "agent_trace": [], "refused": False,
        "refusal_reason": None, "session_id": "s1",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "employee", "user_departments": ["hr"],
        "doc_type": None, "department": None, "session_history": [],
        "verification_passed": False, "verification_reason": "",
        "top_score": 0.0, "retrieved_chunks": [], "answer": None,
        "citations": [], "context_block": None,
    }
    base.update(kwargs)
    return base  # type: ignore[return-value]


def _chunk(idx: int, score: float) -> RetrievedChunk:
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


def _verification(passed: bool, scores: list[float], reason: str) -> VerificationResult:
    chunks = [_chunk(i, s) for i, s in enumerate(scores)]
    retrieval = RetrievalResult(query="q", chunks=chunks, total_candidates=len(chunks))
    top = chunks[0].score if chunks else 0.0
    return VerificationResult(passed=passed, reason=reason, retrieval=retrieval, top_score=top)


@pytest.mark.asyncio
async def test_retriever_passes_when_evidence_sufficient(monkeypatch):
    async def fake_retrieve(**kwargs):
        return _verification(True, [0.82, 0.7, 0.65], "Evidence sufficient.")

    monkeypatch.setattr("agents.retriever.retrieve", fake_retrieve)
    result = await retriever_node(_state())

    assert result["verification_passed"] is True
    assert result["refused"] is False
    assert result["refusal_reason"] is None
    assert len(result["retrieved_chunks"]) == 3
    assert all(isinstance(c, dict) for c in result["retrieved_chunks"])
    assert result["top_score"] == 0.82
    assert "retriever" in result["agent_trace"]


@pytest.mark.asyncio
async def test_retriever_refuses_when_evidence_thin(monkeypatch):
    async def fake_retrieve(**kwargs):
        return VerificationResult(
            passed=False,
            reason="No relevant documents found for your question.",
            retrieval=None,
            top_score=0.0,
        )

    monkeypatch.setattr("agents.retriever.retrieve", fake_retrieve)
    result = await retriever_node(_state())

    assert result["verification_passed"] is False
    assert result["refused"] is True
    assert result["refusal_reason"] == "No relevant documents found for your question."
    assert result["retrieved_chunks"] == []
    assert result["top_score"] == 0.0
    assert "retriever" in result["agent_trace"]


@pytest.mark.asyncio
async def test_retriever_dumps_chunks_to_dicts(monkeypatch):
    async def fake_retrieve(**kwargs):
        return _verification(True, [0.9, 0.8], "Evidence sufficient.")

    monkeypatch.setattr("agents.retriever.retrieve", fake_retrieve)
    result = await retriever_node(_state())

    first = result["retrieved_chunks"][0]
    assert first["filename"] == "handbook.pdf"
    assert first["document_id"] == "doc-123"
    assert first["score"] == 0.9
