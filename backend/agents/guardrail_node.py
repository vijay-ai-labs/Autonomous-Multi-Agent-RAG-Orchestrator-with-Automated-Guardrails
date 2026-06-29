"""Guardrail node: run 4 safety checks on the generated answer.

Order: citation → toxicity → PII → confidence → hallucination (cheap/fast first,
expensive API call last). Short-circuits to ``_flagged`` on the first failure.
``guardrail_passed=True`` → graph routes to persist; ``False`` → routes to escalation.

Never logs answer text — only ``query_id`` + the failing check name.
"""

import asyncio
import logging

from agents.state import AgentState
from core.config import get_settings
from guardrails.citation_check import check_citations
from guardrails.hallucination_check import check_hallucination
from guardrails.pii_check import check_pii
from guardrails.toxicity_check import check_toxicity

logger = logging.getLogger(__name__)


async def guardrail_node(state: AgentState) -> dict:
    """
    Run 4 safety checks on the generated answer.
    Order: citation → toxicity → PII → confidence → hallucination.

    Sets guardrail_passed=True → edge routes to persist.
    Sets guardrail_passed=False → edge routes to escalation.
    Also escalates when top_score < settings.FAITHFULNESS_THRESHOLD.
    """
    settings = get_settings()
    answer = state.get("answer", "") or ""
    context_block = state.get("context_block", "") or ""
    citations = state.get("citations", [])
    details: dict = {}

    # 1. Citation coverage (sync, fast)
    citation_result = check_citations(answer, citations)
    details["citation"] = citation_result
    if not citation_result["passed"]:
        logger.warning("Guardrail FAIL (citation): query=%s", state["query_id"])
        return _flagged(details, "Answer is missing required source citations.")

    # 2. Toxicity (sync, fast)
    toxicity_result = check_toxicity(answer)
    details["toxicity"] = toxicity_result
    if not toxicity_result["passed"]:
        logger.warning("Guardrail FAIL (toxicity): query=%s", state["query_id"])
        return _flagged(details, "Answer contains inappropriate content.")

    # 3. PII (sync presidio — offload to executor)
    loop = asyncio.get_running_loop()
    pii_result = await loop.run_in_executor(None, check_pii, answer)
    details["pii"] = pii_result
    if not pii_result["passed"]:
        logger.warning("Guardrail FAIL (pii): query=%s", state["query_id"])
        return _flagged(details, "Answer may contain personal information.")

    # 4. Confidence threshold
    top_score = state.get("top_score", 0.0)
    if top_score < settings.FAITHFULNESS_THRESHOLD:
        details["confidence"] = {
            "passed": False,
            "detail": f"Top score {top_score:.2f} below threshold {settings.FAITHFULNESS_THRESHOLD}",
        }
        logger.warning("Guardrail FAIL (confidence): query=%s score=%.2f", state["query_id"], top_score)
        return _flagged(details, "Answer confidence too low for automatic approval.")
    details["confidence"] = {"passed": True, "detail": f"Score {top_score:.2f} meets threshold."}

    # 5. Hallucination (async API call — last, most expensive)
    hallucination_result = await check_hallucination(answer, context_block)
    details["hallucination"] = hallucination_result
    if not hallucination_result["passed"]:
        logger.warning("Guardrail FAIL (hallucination): query=%s", state["query_id"])
        return _flagged(details, "Answer may contain claims not supported by documents.")

    logger.info("Guardrail PASS: query=%s", state["query_id"])
    return {
        "guardrail_passed": True,
        "guardrail_result": "approved",
        "guardrail_details": details,
        "agent_trace": ["guardrail"],
    }


def _flagged(details: dict, reason: str) -> dict:
    return {
        "guardrail_passed": False,
        "guardrail_result": "flagged",
        "guardrail_details": details,
        "refused": True,
        "refusal_reason": reason,
        "agent_trace": ["guardrail"],
    }
