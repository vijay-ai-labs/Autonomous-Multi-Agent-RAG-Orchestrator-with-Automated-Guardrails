"""Adversarial: PII detected in a generated answer must flag the guardrail.

Mocks all four guardrail checks (patched in the guardrail_node namespace) so the
test exercises only the node's combination logic — presidio and OpenAI are never
called. Citation + toxicity pass, PII fails; the node must short-circuit to
``flagged`` / ``refused`` before the confidence and hallucination checks.
"""
from unittest.mock import AsyncMock, patch

import pytest

from agents.guardrail_node import guardrail_node

PII_ANSWER = "Contact John Smith at john.smith@company.com for benefits questions [Source 1]."


def _state_with_answer(answer: str, citations: list[dict], top_score: float) -> dict:
    return {
        "query": "who handles benefits?", "query_id": "test-pii-001",
        "route": "retrieve", "route_reason": None,
        "refused": False, "refusal_reason": None, "agent_trace": [],
        "session_id": "s1", "user_id": "00000000-0000-0000-0000-000000000001",
        "user_role": "employee", "user_departments": ["hr"], "doc_type": None,
        "department": None, "session_history": [],
        "verification_passed": True, "verification_reason": "Evidence sufficient.",
        "top_score": top_score, "retrieved_chunks": [],
        "answer": answer, "citations": citations,
        "context_block": "John Smith handles benefits.",
        "guardrail_passed": False, "guardrail_result": "",
        "guardrail_details": {}, "escalation_id": None,
    }


@pytest.mark.asyncio
async def test_pii_in_answer_triggers_guardrail():
    """PII detected in the answer must flag the guardrail and refuse."""
    state = _state_with_answer(
        PII_ANSWER,
        citations=[{"source_num": 1, "filename": "handbook.pdf"}],
        top_score=0.9,
    )

    fake_pii_result = {
        "passed": False,
        "detail": "PII detected: ['EMAIL_ADDRESS']",
        "entities_found": ["EMAIL_ADDRESS"],
    }

    with patch(
        "agents.guardrail_node.check_citations",
        return_value={"passed": True, "detail": "ok", "citation_count": 1},
    ), patch(
        "agents.guardrail_node.check_toxicity",
        return_value={"passed": True, "detail": "ok"},
    ), patch(
        "agents.guardrail_node.check_pii", return_value=fake_pii_result
    ), patch(
        "agents.guardrail_node.check_hallucination",
        AsyncMock(return_value={"passed": True, "detail": "PASS"}),
    ):
        result = await guardrail_node(state)

    assert result["guardrail_passed"] is False
    assert result["guardrail_result"] == "flagged"
    assert result["refused"] is True
