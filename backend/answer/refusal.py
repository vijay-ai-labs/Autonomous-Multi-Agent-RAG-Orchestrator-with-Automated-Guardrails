"""Build structured refusal responses when evidence verification fails."""

from answer.schemas import RefusalResponse

REFUSAL_TEMPLATE = (
    "I don't have reliable information in the company documents to answer this question.\n\n"
    "Reason: {reason}\n\n"
    "If this is urgent, please contact the relevant team directly. "
    "A record of this question has been logged for the knowledge team to review."
)


def build_refusal(
    query_id: str,
    session_id: str,
    reason: str,
) -> RefusalResponse:
    """Construct a user-facing refusal from a verification ``reason``."""
    return RefusalResponse(
        query_id=query_id,
        session_id=session_id,
        refused=True,
        refusal_reason=reason,
        answer=REFUSAL_TEMPLATE.format(reason=reason),
        citations=[],
        confidence=0.0,
    )
