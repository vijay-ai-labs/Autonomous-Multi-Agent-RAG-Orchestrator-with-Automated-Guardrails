"""Router node: first line of defence against prompt injection + jailbreaks.

Routes safe queries to the Retriever and refuses malicious ones. It deliberately
does NOT judge topic/domain — "the answer isn't in our docs" is the Verifier's job.
An off-topic but benign question must reach the Retriever and be refused there with a
clean evidence message, not blocked here.
"""

import logging
import re

from agents.state import AgentState

logger = logging.getLogger(__name__)

# ── Injection patterns ─────────────────────────────────────────────────────────
# Matches attempts to override the system prompt or reveal instructions.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"(disregard|forget|override)\s+(your\s+)?(instructions?|system\s+prompt|rules?)", re.I),
    re.compile(r"you\s+are\s+now\s+a?\s*(new|different|another)?\s*(ai|assistant|bot|model)", re.I),
    re.compile(r"(act|pretend|behave|respond)\s+as\s+(if\s+)?(you\s+are|you're|a)\s+", re.I),
    # Roleplay framing without the literal "as": "pretend you are…", "act like you're…".
    re.compile(r"(pretend|imagine|act|roleplay|behave)\s+(like\s+|that\s+)?(you\s+are|you're|to\s+be)\b", re.I),
    re.compile(r"system\s*prompt\s*:", re.I),
    re.compile(r"<\s*(system|SYSTEM)\s*>", re.I),
    re.compile(r"\[\s*system\s*\]", re.I),
    re.compile(r"###\s*(instruction|system|new role)", re.I),
    re.compile(r"print\s+(your\s+)?(system\s+)?prompt", re.I),
    re.compile(r"reveal\s+(your\s+)?(instructions?|system\s+prompt|context)", re.I),
]

# ── Jailbreak keywords ─────────────────────────────────────────────────────────
_JAILBREAK_KEYWORDS: list[str] = [
    "jailbreak", "dan mode", "developer mode", "god mode",
    "unrestricted mode", "no restrictions", "no rules", "bypass safety",
    "ignore safety", "without filters", "remove guardrails",
    "enable adult", "nsfw mode",
]


def _detect_injection(query: str) -> str | None:
    """Return a reason string if injection/jailbreak detected, else None."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(query):
            return f"Prompt injection pattern detected: '{pattern.pattern[:60]}'"
    q_lower = query.lower()
    for kw in _JAILBREAK_KEYWORDS:
        if kw in q_lower:
            return f"Jailbreak keyword detected: '{kw}'"
    return None


def router_node(state: AgentState) -> dict:
    """Classify the query as safe (route=retrieve) or malicious (route=refuse).

    Synchronous by design — pure regex/string work, no I/O. Returns a partial
    state update.
    """
    query = state["query"]

    # Length guard (already validated in the API layer but enforced here too).
    if len(query.strip()) == 0:
        return {"route": "refuse", "route_reason": "Empty query.", "agent_trace": ["router"]}

    injection_reason = _detect_injection(query)
    if injection_reason:
        logger.warning("Router blocked query %s: %s", state["query_id"], injection_reason)
        return {
            "route": "refuse",
            "route_reason": "Your query was flagged as a potential prompt injection attempt "
                            "and cannot be processed. If you believe this is an error, "
                            "please rephrase your question.",
            "refused": True,
            "refusal_reason": injection_reason,
            "agent_trace": ["router"],
        }

    logger.info("Router approved query %s → retrieve", state["query_id"])
    return {"route": "retrieve", "agent_trace": ["router"]}
