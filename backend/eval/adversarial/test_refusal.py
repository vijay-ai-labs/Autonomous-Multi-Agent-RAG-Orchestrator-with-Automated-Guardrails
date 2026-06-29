"""Adversarial: out-of-domain queries must fail evidence verification.

Mocks ``retrieve()`` (patched in the retriever module namespace) to return an
insufficient-evidence ``VerificationResult``. The retriever node must propagate
that into ``verification_passed=False`` and ``refused=True`` for every query.
No Qdrant, no OpenAI.
"""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agents.retriever import retriever_node
from retrieval.schemas import VerificationResult

REFUSAL_QUERIES = json.loads(
    (Path(__file__).parent.parent / "datasets" / "refusal_queries.json").read_text(
        encoding="utf-8"
    )
)


def _state(query: str) -> dict:
    return {
        "query": query, "query_id": "test-001", "route": "retrieve",
        "route_reason": None, "refused": False, "refusal_reason": None,
        "agent_trace": [], "session_id": "s1",
        "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "employee", "user_departments": ["hr"],
        "doc_type": None, "department": None, "session_history": [],
        "verification_passed": False, "verification_reason": "",
        "top_score": 0.0, "retrieved_chunks": [], "answer": None,
        "citations": [], "context_block": None,
        "guardrail_passed": False, "guardrail_result": "",
        "guardrail_details": {}, "escalation_id": None,
    }


def _make_verification(passed: bool, reason: str) -> VerificationResult:
    return VerificationResult(
        passed=passed, reason=reason, retrieval=None, top_score=0.0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("query", REFUSAL_QUERIES)
async def test_out_of_domain_refused(query: str):
    """Out-of-domain queries must fail evidence verification."""
    fake_verification = _make_verification(
        passed=False, reason="No relevant documents found."
    )
    with patch(
        "agents.retriever.retrieve", AsyncMock(return_value=fake_verification)
    ):
        result = await retriever_node(_state(query))

    assert result["verification_passed"] is False, (
        f"Retriever did not refuse out-of-domain query: '{query[:100]}'"
    )
    assert result["refused"] is True
