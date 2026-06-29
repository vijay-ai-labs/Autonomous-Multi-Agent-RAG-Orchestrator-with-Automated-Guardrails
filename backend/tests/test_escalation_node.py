"""Tests for the escalation flow.

The escalation_node is pure (no DB/email) per the FK-safe design: it only mints a
ticket ID and the user-facing message. The DB write + email happen in persist_node,
covered by the persist-path tests below.
"""

from uuid import UUID, uuid4

import pytest

from agents import persist_node as pn
from agents.escalation_node import _REASON_CODE_MAP, escalation_node
from agents.persist_node import persist_node
from models.tables import AuditLog, Escalation, Query, Response

# --------------------------------------------------------------------------
# escalation_node (pure)
# --------------------------------------------------------------------------


def _state(**overrides) -> dict:
    base = {
        "query_id": str(uuid4()),
        "refusal_reason": "Answer is missing required source citations.",
        "guardrail_details": {"citation": {"passed": False}},
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_escalation_node_sets_ticket_and_message():
    result = await escalation_node(_state())
    assert result["escalation_id"] is not None
    UUID(result["escalation_id"])  # valid uuid
    assert result["refused"] is True
    assert "#" in result["answer"]
    # ticket in message is the 8-char uppercase prefix
    ticket = result["escalation_id"][:8].upper()
    assert ticket in result["answer"]
    assert "escalation" in result["agent_trace"]


@pytest.mark.asyncio
async def test_escalation_node_preserves_reason():
    result = await escalation_node(_state(refusal_reason="Answer contains inappropriate content."))
    assert result["refusal_reason"] == "Answer contains inappropriate content."


def test_reason_code_map_covers_all_guardrail_reasons():
    assert _REASON_CODE_MAP["Answer is missing required source citations."] == "missing_citations"
    assert _REASON_CODE_MAP["Answer contains inappropriate content."] == "toxicity"
    assert _REASON_CODE_MAP["Answer may contain personal information."] == "pii_detected"
    assert _REASON_CODE_MAP["Answer confidence too low for automatic approval."] == "low_confidence"
    assert _REASON_CODE_MAP["Answer may contain claims not supported by documents."] == "hallucination"


# --------------------------------------------------------------------------
# persist_node escalation path (DB write + email)
# --------------------------------------------------------------------------


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list = []
        self.committed = False

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _persist_state(escalation_id: str) -> dict:
    return {
        "query_id": str(uuid4()),
        "session_id": "sess-1",
        "user_id": str(uuid4()),
        "query": "What is the vacation policy?",
        "refused": True,
        "citations": [],
        "top_score": 0.5,
        "guardrail_result": "flagged",
        "guardrail_details": {"citation": {"passed": False}},
        "refusal_reason": "Answer is missing required source citations.",
        "escalation_id": escalation_id,
        "answer": f"...Ticket: #{escalation_id[:8].upper()}...",
        "route": "retrieve",
        "agent_trace": ["router", "retriever", "answer", "guardrail", "escalation"],
    }


@pytest.mark.asyncio
async def test_persist_writes_escalation_and_emails(monkeypatch):
    session = _RecordingSession()
    monkeypatch.setattr(pn, "async_session_factory", lambda: session)
    email_calls: list = []
    monkeypatch.setattr(
        "notifications.email_service.send_escalation_email",
        lambda *a, **kw: email_calls.append(a) or False,
    )

    escalation_id = str(uuid4())
    result = await persist_node(_persist_state(escalation_id))

    assert session.committed is True
    types_added = [type(o) for o in session.added]
    assert Query in types_added
    assert Response in types_added
    assert Escalation in types_added
    assert AuditLog in types_added

    escalation_row = next(o for o in session.added if isinstance(o, Escalation))
    assert str(escalation_row.id) == escalation_id
    assert escalation_row.reason_code == "missing_citations"
    assert escalation_row.status == "open"

    response_row = next(o for o in session.added if isinstance(o, Response))
    assert response_row.guardrail_result == "flagged"

    assert len(email_calls) == 1
    assert "persist" in result["agent_trace"]


@pytest.mark.asyncio
async def test_persist_email_failure_does_not_propagate(monkeypatch):
    session = _RecordingSession()
    monkeypatch.setattr(pn, "async_session_factory", lambda: session)

    def _boom(*a, **kw):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr("notifications.email_service.send_escalation_email", _boom)

    escalation_id = str(uuid4())
    # Must not raise — escalation is already committed.
    result = await persist_node(_persist_state(escalation_id))
    assert session.committed is True
    assert "persist" in result["agent_trace"]
