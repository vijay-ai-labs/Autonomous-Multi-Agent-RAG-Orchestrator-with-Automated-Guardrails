"""Retriever node: thin async wrapper over the retrieval pipeline.

``retrieve()`` already runs search → rerank → evidence verification, so this node
only calls it and projects the ``VerificationResult`` into state. Chunks are stored
as plain dicts (``model_dump``) so the state stays JSON-serialisable for tracing.
"""

import logging
from uuid import UUID

from agents.state import AgentState
from core.access import UserScope
from retrieval.service import retrieve

logger = logging.getLogger(__name__)


async def retriever_node(state: AgentState) -> dict:
    """Call the retrieval pipeline and store ``VerificationResult`` fields in state."""
    scope = UserScope(
        id=UUID(state["user_id"]),
        role=state["user_role"],
        departments=tuple(state.get("user_departments") or []),
    )
    verification = await retrieve(
        query=state["query"],
        scope=scope,
        doc_type=state.get("doc_type"),
        department=state.get("department"),
    )
    chunk_count = len(verification.retrieval.chunks) if verification.retrieval else 0
    logger.info(
        "Retriever: query=%s passed=%s top_score=%.3f chunks=%d",
        state["query_id"],
        verification.passed,
        verification.top_score,
        chunk_count,
    )

    chunks = []
    if verification.retrieval:
        chunks = [c.model_dump() for c in verification.retrieval.chunks]

    return {
        "verification_passed": verification.passed,
        "verification_reason": verification.reason,
        "top_score": verification.top_score,
        "retrieved_chunks": chunks,
        "refused": not verification.passed,
        "refusal_reason": verification.reason if not verification.passed else None,
        "agent_trace": ["retriever"],
    }
