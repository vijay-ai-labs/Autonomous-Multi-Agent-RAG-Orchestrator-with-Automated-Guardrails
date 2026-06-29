"""Escalation node: build the user-facing refusal message + ticket ID.

Pure node — does NO DB or email I/O. ``persist_node`` is the graph's sole DB boundary;
it inserts the Escalation + AuditLog rows (after the parent Query row exists, satisfying
the FK) and fires the notification email off the request path. This node only generates
the ``escalation_id``, composes the ticket message, and marks the turn refused.
"""

import logging
from uuid import uuid4

from agents.state import AgentState

logger = logging.getLogger(__name__)

# Maps a guardrail refusal_reason → a stable reason_code stored on the Escalation row.
# Imported by persist_node to derive reason_code at insert time.
_REASON_CODE_MAP = {
    "Answer is missing required source citations.": "missing_citations",
    "Answer contains inappropriate content.": "toxicity",
    "Answer may contain personal information.": "pii_detected",
    "Answer confidence too low for automatic approval.": "low_confidence",
    "Answer may contain claims not supported by documents.": "hallucination",
}


async def escalation_node(state: AgentState) -> dict:
    """
    Generate an escalation ticket ID and a user-facing refusal message.
    The actual DB write + email are performed by persist_node (FK-safe ordering).
    """
    escalation_id = str(uuid4())
    reason = state.get("refusal_reason", "Unknown guardrail failure")

    user_message = (
        "I don't have reliable information to answer this question reliably.\n\n"
        f"Reason: {reason}\n\n"
        f"Your query has been escalated for human review (Ticket: #{escalation_id[:8].upper()}). "
        "The relevant team has been notified and will follow up."
    )

    logger.info(
        "Escalation queued: ticket=%s query=%s",
        escalation_id[:8], state["query_id"],
    )
    return {
        "escalation_id": escalation_id,
        "answer": user_message,
        "refusal_reason": reason,
        "refused": True,
        "agent_trace": ["escalation"],
    }
