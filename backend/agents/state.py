"""Shared state flowing through every node of the agent graph.

A single ``TypedDict`` is threaded through Router → Retriever → Answer → Persist.
Each node returns a *partial* update (a plain dict) which LangGraph merges into the
running state. ``agent_trace`` is the one field with a reducer: its
``Annotated[..., operator.add]`` tells LangGraph to APPEND each node's contribution
(e.g. ``["router"]``) rather than overwrite, yielding a full visit trace.
"""

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    # ── Input (set before graph.ainvoke) ──────────────────────────────────
    query: str
    session_id: str                     # always set (generated if client sent None)
    user_id: str                        # UUID as string
    user_role: str                      # "admin" | "manager" | "employee"
    user_departments: list[str]         # RBAC scope; empty = admin (all)
    doc_type: str | None
    department: str | None
    query_id: str                       # UUID as string, generated before invocation
    session_history: list[dict]         # loaded from Redis before invocation

    # ── Router output ─────────────────────────────────────────────────────
    route: str                          # "retrieve" | "refuse"
    route_reason: str | None            # set when route="refuse"

    # ── Retriever output ──────────────────────────────────────────────────
    verification_passed: bool
    verification_reason: str
    top_score: float
    retrieved_chunks: list[dict]        # list of RetrievedChunk.model_dump()

    # ── Answer output ─────────────────────────────────────────────────────
    answer: str | None
    citations: list[dict]               # list of Citation.model_dump()
    context_block: str | None           # stored for Guardrail in Phase 2

    # ── Guardrail output ──────────────────────────────────────────────────────
    guardrail_passed: bool
    guardrail_result: str           # "approved" | "flagged"
    guardrail_details: dict         # {check_name: {passed: bool, detail: str}}

    # ── Escalation output ─────────────────────────────────────────────────────
    escalation_id: str | None       # UUID of escalation record if created

    # ── Final flags ───────────────────────────────────────────────────────
    refused: bool
    refusal_reason: str | None

    # ── Tracing ───────────────────────────────────────────────────────────
    agent_trace: Annotated[list[str], operator.add]   # accumulates node names
