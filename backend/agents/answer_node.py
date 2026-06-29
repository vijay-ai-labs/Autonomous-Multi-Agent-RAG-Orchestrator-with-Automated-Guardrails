"""Answer node: format retrieved evidence and generate a grounded answer.

Only reached when the Retriever set ``verification_passed=True``. Rehydrates the
chunk dicts back into ``RetrievedChunk`` models, formats a context block + citations,
then calls the LLM. ``context_block`` is kept in state for the SP3 Phase 2 Guardrail.
"""

import logging

from agents.state import AgentState
from answer.formatter import format_context
from answer.generator import generate_answer
from retrieval.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


async def answer_node(state: AgentState) -> dict:
    """Format context and generate a grounded answer with citations."""
    chunks = [RetrievedChunk(**c) for c in state["retrieved_chunks"]]
    context_block, citations = format_context(chunks)

    answer_text = await generate_answer(
        query=state["query"],
        context_block=context_block,
        session_history=state.get("session_history", []),
    )
    logger.info(
        "Answer node: query=%s citations=%d",
        state["query_id"],
        len(citations),
    )
    return {
        "answer": answer_text,
        "citations": [c.model_dump() for c in citations],
        "context_block": context_block,
        "refused": False,
        "agent_trace": ["answer"],
    }
