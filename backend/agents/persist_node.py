"""Persist node: the graph's only DB/Redis I/O boundary.

Keeping all persistence here leaves every other node pure and trivially testable.
It opens its OWN ``async_session_factory`` session — never the FastAPI request session,
which belongs to the request lifecycle, not the graph's. Writes a Query + Response row
(plus an AuditLog row on refusal) and, for answered queries, appends the turn to Redis.
"""

import asyncio
import logging
from uuid import UUID

from agents.state import AgentState
from answer.session import save_session
from core.database import async_session_factory
from models.tables import AuditLog, Escalation, Query, Response

logger = logging.getLogger(__name__)


async def persist_node(state: AgentState) -> dict:
    """Write query + response to Postgres. Update session in Redis."""
    query_id = UUID(state["query_id"])
    session_id = state["session_id"]
    refused = state.get("refused", False)
    citations = state.get("citations", [])
    escalation_id = state.get("escalation_id")
    # Escalations carry their own ticket message in ``answer``; plain refusals use template.
    if escalation_id:
        answer_text = state.get("answer") or ""
    else:
        answer_text = _build_refusal_text(state) if refused else (state.get("answer") or "")
    # Prefer the guardrail's verdict; fall back to legacy refused/approved.
    guardrail_result = state.get("guardrail_result") or ("refused" if refused else "approved")
    # Full visit trace (this node's own contribution is appended after return).
    agent_trace_id = "->".join(state.get("agent_trace", []) + ["persist"])

    async with async_session_factory() as db:
        db.add(Query(
            id=query_id,
            session_id=session_id,
            user_id=UUID(state["user_id"]),
            query_text=state["query"],
            agent_trace_id=agent_trace_id,
        ))
        db.add(Response(
            query_id=query_id,
            answer_text=answer_text,
            citations=citations,
            confidence_score=state.get("top_score", 0.0),
            guardrail_result=guardrail_result,
            guardrail_details=state.get("guardrail_details") or (
                {"reason": state.get("refusal_reason")} if refused else None
            ),
        ))
        # Escalation row — written here (not in escalation_node) so the parent Query
        # row above satisfies the escalations.query_id FK within one transaction.
        if escalation_id:
            from agents.escalation_node import _REASON_CODE_MAP

            reason = state.get("refusal_reason", "")
            reason_code = _REASON_CODE_MAP.get(reason, "guardrail_failure")
            db.add(Escalation(
                id=UUID(escalation_id),
                query_id=query_id,
                reason_code=reason_code,
                status="open",
            ))
            db.add(AuditLog(
                event_type="escalation_created",
                entity_id=UUID(escalation_id),
                agent_name="escalation",
                details={
                    "query_id": state["query_id"],
                    "reason": reason,
                    "guardrail_details": state.get("guardrail_details", {}),
                },
            ))
        elif refused:
            db.add(AuditLog(
                event_type="refusal",
                entity_id=query_id,
                details={
                    "reason": state.get("refusal_reason"),
                    "query": state["query"][:200],
                    "route": state.get("route"),
                },
            ))
        await db.commit()

    # Notify the escalation team off the request path (SMTP is blocking). The email
    # service never raises by contract; the guard is belt-and-suspenders so a broken
    # notifier can never fail an already-committed escalation.
    if escalation_id:
        from notifications.email_service import send_escalation_email

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                send_escalation_email,
                escalation_id,
                state["query_id"],
                state.get("refusal_reason", ""),
                state["query"][:200],
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Escalation email dispatch failed (non-fatal): %s", exc)

    # Save session only for answered (non-refused) queries.
    if not refused and state.get("answer"):
        new_history = list(state.get("session_history", [])) + [
            {"role": "user", "content": state["query"]},
            {"role": "assistant", "content": state["answer"]},
        ]
        await save_session(session_id, new_history)

    logger.info("Persist node: query=%s refused=%s", state["query_id"], refused)
    return {"agent_trace": ["persist"]}


def _build_refusal_text(state: AgentState) -> str:
    from answer.refusal import REFUSAL_TEMPLATE

    return REFUSAL_TEMPLATE.format(reason=state.get("refusal_reason", "Unknown reason"))
