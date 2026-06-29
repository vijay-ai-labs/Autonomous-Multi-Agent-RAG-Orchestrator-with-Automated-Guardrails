"""GPT-4o-mini faithfulness check: are the answer's claims supported by the context?

Fail-open: any OpenAI error returns passed=True so a checker outage never blocks a user.
Never logs answer text — only the (truncated) verdict.
"""

import logging

import openai

from core.config import get_settings

logger = logging.getLogger(__name__)

_HALLUCINATION_SYSTEM = """You are a fact-checking assistant. You will be given:
1. CONTEXT: excerpts from company documents
2. ANSWER: an AI-generated response

Your task: determine if the ANSWER contains any factual claims NOT supported by the CONTEXT.
A claim is unsupported if it cannot be verified from the provided CONTEXT excerpts.
Respond with exactly one of:
- "PASS: <brief reason>" — all claims are supported by the context
- "FAIL: <specific unsupported claim>" — found at least one unsupported claim
Do not add any other text."""


async def check_hallucination(
    answer: str,
    context_block: str,
) -> dict:
    """
    Returns: {"passed": bool, "detail": str}
    On OpenAI error: returns {"passed": True, "detail": "check skipped: <error>"}
    (fail-open: don't block answer if checker itself fails)
    """
    settings = get_settings()
    prompt = f"CONTEXT:\n{context_block}\n\nANSWER:\n{answer}"
    try:
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=settings.OPENAI_GUARDRAIL_MODEL,   # gpt-4o-mini
            messages=[
                {"role": "system", "content": _HALLUCINATION_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=150,
        )
        verdict = response.choices[0].message.content.strip()
        passed = verdict.upper().startswith("PASS")
        logger.info("Hallucination check verdict: %s", verdict[:80])
        return {"passed": passed, "detail": verdict}
    except Exception as exc:
        logger.warning("Hallucination check skipped due to error: %s", exc)
        return {"passed": True, "detail": f"check skipped: {exc}"}
