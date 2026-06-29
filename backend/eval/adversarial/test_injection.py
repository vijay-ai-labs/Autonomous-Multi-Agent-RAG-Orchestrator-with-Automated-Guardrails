"""Adversarial: every prompt-injection query must be refused by the router.

Calls ``router_node`` directly (sync, pure regex) — no mocks, no API calls.
"""
import json
from pathlib import Path

import pytest

from agents.router import router_node

INJECTION_QUERIES = json.loads(
    (Path(__file__).parent.parent / "datasets" / "injection_queries.json").read_text(
        encoding="utf-8"
    )
)


def _state(query: str) -> dict:
    return {
        "query": query, "query_id": "test-001", "route": "",
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


@pytest.mark.parametrize("query", INJECTION_QUERIES)
def test_injection_query_refused(query: str):
    """Every injection query must be refused by the router."""
    result = router_node(_state(query))
    assert result.get("route") == "refuse", (
        f"Router FAILED to block injection: '{query[:100]}'"
    )
    assert result.get("refused") is True
