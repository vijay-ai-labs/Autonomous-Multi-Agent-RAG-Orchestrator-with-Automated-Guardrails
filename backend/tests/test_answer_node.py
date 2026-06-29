"""Tests for the async Answer node (format_context + generate_answer mocked)."""

from unittest.mock import AsyncMock

import pytest

from agents.answer_node import answer_node
from agents.state import AgentState
from answer.schemas import Citation


def _chunk_dict() -> dict:
    return {
        "chunk_index": 0,
        "content": "Employees accrue 20 vacation days per year.",
        "page_number": 3,
        "section": "Leave",
        "filename": "handbook.pdf",
        "doc_type": "policy",
        "department": "hr",
        "document_id": "doc-123",
        "score": 0.82,
        "search_score": 0.5,
    }


def _citation() -> Citation:
    return Citation(
        source_num=1,
        filename="handbook.pdf",
        page_number=3,
        section="Leave",
        excerpt="Employees accrue 20 vacation days per year.",
        document_id="doc-123",
    )


def _state(**kwargs) -> AgentState:
    base = {
        "query": "How many vacation days?", "query_id": "abc", "route": "retrieve",
        "route_reason": None, "agent_trace": [], "refused": False,
        "refusal_reason": None, "session_id": "s1", "user_id": "u1",
        "doc_type": None, "department": None, "session_history": [],
        "verification_passed": True, "verification_reason": "Evidence sufficient.",
        "top_score": 0.82, "retrieved_chunks": [_chunk_dict()], "answer": None,
        "citations": [], "context_block": None,
    }
    base.update(kwargs)
    return base  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_answer_node_formats_and_generates(monkeypatch):
    def fake_format_context(chunks):
        return "CTX BLOCK", [_citation()]

    monkeypatch.setattr("agents.answer_node.format_context", fake_format_context)
    monkeypatch.setattr(
        "agents.answer_node.generate_answer",
        AsyncMock(return_value="You get 20 vacation days [Source 1]."),
    )

    result = await answer_node(_state())

    assert result["answer"] == "You get 20 vacation days [Source 1]."
    assert len(result["citations"]) == 1
    assert all(isinstance(c, dict) for c in result["citations"])
    assert result["context_block"] == "CTX BLOCK"
    assert result["refused"] is False
    assert "answer" in result["agent_trace"]


@pytest.mark.asyncio
async def test_answer_node_forwards_session_history(monkeypatch):
    history = [{"role": "user", "content": "earlier question"}]
    gen_mock = AsyncMock(return_value="answer text")
    monkeypatch.setattr(
        "agents.answer_node.format_context", lambda chunks: ("CTX", [_citation()])
    )
    monkeypatch.setattr("agents.answer_node.generate_answer", gen_mock)

    await answer_node(_state(session_history=history))

    gen_mock.assert_awaited_once()
    assert gen_mock.await_args.kwargs["session_history"] == history
    assert gen_mock.await_args.kwargs["context_block"] == "CTX"
