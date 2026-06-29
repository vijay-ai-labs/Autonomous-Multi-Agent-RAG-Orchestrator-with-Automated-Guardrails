"""Tests for the guardrail node: routing + short-circuit ordering.

All 4 check functions are monkeypatched on ``agents.guardrail_node`` so no real
presidio/OpenAI work happens. Verifies approve vs flag and that the expensive
hallucination check is NOT called once an earlier check fails.
"""

from unittest.mock import AsyncMock

import pytest

from agents import guardrail_node as gn
from agents.guardrail_node import guardrail_node


def _state(**overrides) -> dict:
    base = {
        "query_id": "q-1",
        "answer": "Policy says 15 days [Source 1].",
        "citations": [{"source_num": 1}],
        "context_block": "ctx",
        "top_score": 0.8,
    }
    base.update(overrides)
    return base


def _patch_all_pass(monkeypatch):
    monkeypatch.setattr(gn, "check_citations",
                        lambda a, c: {"passed": True, "detail": "ok", "citation_count": 2})
    monkeypatch.setattr(gn, "check_toxicity",
                        lambda t: {"passed": True, "detail": "ok"})
    monkeypatch.setattr(gn, "check_pii",
                        lambda t: {"passed": True, "detail": "ok", "entities_found": []})
    hallu = AsyncMock(return_value={"passed": True, "detail": "PASS: ok"})
    monkeypatch.setattr(gn, "check_hallucination", hallu)
    return hallu


@pytest.mark.asyncio
async def test_guardrail_approves_clean_answer(monkeypatch):
    _patch_all_pass(monkeypatch)
    result = await guardrail_node(_state())
    assert result["guardrail_passed"] is True
    assert result["guardrail_result"] == "approved"
    assert "guardrail" in result["agent_trace"]
    assert result["guardrail_details"]["confidence"]["passed"] is True


@pytest.mark.asyncio
async def test_citation_failure_flags(monkeypatch):
    _patch_all_pass(monkeypatch)
    monkeypatch.setattr(gn, "check_citations",
                        lambda a, c: {"passed": False, "detail": "none", "citation_count": 0})
    result = await guardrail_node(_state())
    assert result["guardrail_passed"] is False
    assert result["guardrail_result"] == "flagged"
    assert result["refused"] is True
    assert result["refusal_reason"] == "Answer is missing required source citations."
    assert "guardrail" in result["agent_trace"]


@pytest.mark.asyncio
async def test_toxicity_failure_short_circuits(monkeypatch):
    hallu = _patch_all_pass(monkeypatch)
    monkeypatch.setattr(gn, "check_toxicity",
                        lambda t: {"passed": False, "detail": "bad"})
    result = await guardrail_node(_state())
    assert result["guardrail_passed"] is False
    assert result["refusal_reason"] == "Answer contains inappropriate content."
    hallu.assert_not_called()


@pytest.mark.asyncio
async def test_pii_failure_flags(monkeypatch):
    hallu = _patch_all_pass(monkeypatch)
    monkeypatch.setattr(gn, "check_pii",
                        lambda t: {"passed": False, "detail": "pii", "entities_found": ["EMAIL_ADDRESS"]})
    result = await guardrail_node(_state())
    assert result["guardrail_passed"] is False
    assert result["refusal_reason"] == "Answer may contain personal information."
    hallu.assert_not_called()


@pytest.mark.asyncio
async def test_low_confidence_short_circuits(monkeypatch):
    hallu = _patch_all_pass(monkeypatch)
    result = await guardrail_node(_state(top_score=0.5))
    assert result["guardrail_passed"] is False
    assert result["refusal_reason"] == "Answer confidence too low for automatic approval."
    assert result["guardrail_details"]["confidence"]["passed"] is False
    hallu.assert_not_called()


@pytest.mark.asyncio
async def test_hallucination_failure_flags(monkeypatch):
    _patch_all_pass(monkeypatch)
    monkeypatch.setattr(gn, "check_hallucination",
                        AsyncMock(return_value={"passed": False, "detail": "FAIL: bad"}))
    result = await guardrail_node(_state())
    assert result["guardrail_passed"] is False
    assert result["refusal_reason"] == "Answer may contain claims not supported by documents."
    assert "guardrail" in result["agent_trace"]
