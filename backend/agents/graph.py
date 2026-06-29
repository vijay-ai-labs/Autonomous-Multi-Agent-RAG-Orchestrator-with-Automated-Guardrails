"""LangGraph StateGraph wiring the four agent nodes together.

Flow:    router ─(safe)→ retriever ─(evidence ok)→ answer → persist → END
                 └(refuse)→ persist               └(thin)→ persist

The ``answer → persist`` edge is where SP3 Phase 2 inserts the Guardrail + Escalation
nodes — Router/Retriever/Answer stay frozen. ``compiled_graph`` is a module-level
singleton: import it, never rebuild per request.
"""

import logging

from langgraph.graph import END, StateGraph

from agents.answer_node import answer_node
from agents.escalation_node import escalation_node
from agents.guardrail_node import guardrail_node
from agents.persist_node import persist_node
from agents.retriever import retriever_node
from agents.router import router_node
from agents.state import AgentState

logger = logging.getLogger(__name__)


def _route_after_router(state: AgentState) -> str:
    """Edge: Router → Retriever (safe) or Persist (refused)."""
    return "retriever" if state.get("route") == "retrieve" else "persist"


def _route_after_retriever(state: AgentState) -> str:
    """Edge: Retriever → Answer (evidence ok) or Persist (insufficient evidence)."""
    return "answer" if state.get("verification_passed") else "persist"


def _route_after_guardrail(state: AgentState) -> str:
    """Edge: Guardrail → Persist (approved) or Escalation (flagged)."""
    return "persist" if state.get("guardrail_passed") else "escalation"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("answer", answer_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("persist", persist_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {"retriever": "retriever", "persist": "persist"},
    )
    graph.add_conditional_edges(
        "retriever",
        _route_after_retriever,
        {"answer": "answer", "persist": "persist"},
    )
    graph.add_edge("answer", "guardrail")
    graph.add_conditional_edges(
        "guardrail",
        _route_after_guardrail,
        {"persist": "persist", "escalation": "escalation"},
    )
    graph.add_edge("escalation", "persist")
    graph.add_edge("persist", END)

    return graph


# Module-level compiled singleton — import this in pipeline.py.
compiled_graph = build_graph().compile()
