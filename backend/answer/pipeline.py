"""Top-level query pipeline: now a thin driver over the SP3 agent graph.

Builds the initial ``AgentState``, invokes the compiled LangGraph graph
(router → retriever → answer → persist), and maps the final state back to a
:class:`QueryResponse`. The graph's persist node owns all DB/Redis I/O, so the
``db`` session passed from the API layer is kept only for signature compatibility.

Always returns a :class:`QueryResponse`; refusals carry ``refused=True``. Never logs
full query/answer text (PII) — correlation is by ``query_id``.
"""

import logging
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import compiled_graph
from answer.schemas import Citation, QueryResponse
from answer.session import load_session

logger = logging.getLogger(__name__)


async def run_query_pipeline(
    query_text: str,
    session_id: str | None,
    user_id: UUID,
    user_role: str,
    user_departments: list[str],
    doc_type: str | None,
    department: str | None,
    db: AsyncSession,           # kept for signature compat; persist node uses its own session
) -> QueryResponse:
    """Entry point: build initial state, invoke graph, return QueryResponse."""
    session_id, session_history = await load_session(session_id)
    query_id = str(uuid.uuid4())

    initial_state: dict = {
        "query": query_text,
        "session_id": session_id,
        "user_id": str(user_id),
        "user_role": user_role,
        "user_departments": user_departments,
        "doc_type": doc_type,
        "department": department,
        "query_id": query_id,
        "session_history": session_history,
        "route": "",
        "route_reason": None,
        "verification_passed": False,
        "verification_reason": "",
        "top_score": 0.0,
        "retrieved_chunks": [],
        "answer": None,
        "citations": [],
        "context_block": None,
        "guardrail_passed": False,
        "guardrail_result": "",
        "guardrail_details": {},
        "escalation_id": None,
        "refused": False,
        "refusal_reason": None,
        "agent_trace": [],
    }

    final_state = await compiled_graph.ainvoke(initial_state)

    logger.info(
        "Graph completed: query=%s trace=%s refused=%s",
        query_id,
        final_state.get("agent_trace"),
        final_state.get("refused"),
    )

    return QueryResponse(
        query_id=query_id,
        session_id=session_id,
        answer=final_state.get("answer") or _refusal_answer(final_state),
        citations=[Citation(**c) for c in final_state.get("citations", [])],
        confidence=final_state.get("top_score", 0.0),
        refused=final_state.get("refused", False),
        refusal_reason=final_state.get("refusal_reason"),
    )


def _refusal_answer(state: dict) -> str:
    from answer.refusal import REFUSAL_TEMPLATE

    return REFUSAL_TEMPLATE.format(reason=state.get("refusal_reason", "Insufficient information."))
