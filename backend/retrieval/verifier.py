"""Evidence sufficiency check — pure, synchronous, no I/O.

Decides whether retrieved chunks are good enough to ground an answer. The
``reason`` string is shown verbatim to users in refusal messages.
"""

from core.config import get_settings
from retrieval.schemas import RetrievalResult, VerificationResult

MIN_CHUNKS = 2


def verify_evidence(retrieval: RetrievalResult) -> VerificationResult:
    """Check whether retrieved evidence is sufficient to answer.

    Passes only when ALL hold:
    - at least one chunk was retrieved,
    - at least :data:`MIN_CHUNKS` chunks were retrieved,
    - the top chunk's reranker score >= ``settings.EVIDENCE_THRESHOLD``.
    """
    settings = get_settings()
    chunks = retrieval.chunks
    top_score = chunks[0].score if chunks else 0.0

    if not chunks:
        return VerificationResult(
            passed=False,
            reason="No relevant documents found for your question.",
            retrieval=retrieval,
            top_score=0.0,
        )
    if len(chunks) < MIN_CHUNKS:
        return VerificationResult(
            passed=False,
            reason="Insufficient evidence found. Only one document chunk matched "
            "and that is not enough to answer reliably.",
            retrieval=retrieval,
            top_score=top_score,
        )
    if top_score < settings.EVIDENCE_THRESHOLD:
        return VerificationResult(
            passed=False,
            reason=f"Retrieved documents are not relevant enough to answer this question "
            f"(confidence: {top_score:.0%}). Please rephrase or contact the relevant team.",
            retrieval=retrieval,
            top_score=top_score,
        )

    return VerificationResult(
        passed=True,
        reason="Evidence sufficient.",
        retrieval=retrieval,
        top_score=top_score,
    )
