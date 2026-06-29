"""Pydantic models for the retrieval pipeline outputs.

These are the data contracts SP2 Phase 2 reads from :func:`retrieval.service.retrieve`.
"""

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """A single reranked chunk with its source metadata and scores."""

    chunk_index: int
    content: str
    page_number: int | None
    section: str | None
    filename: str = Field(..., description="Stored filename from the Qdrant payload")
    doc_type: str
    department: str | None
    document_id: str
    score: float = Field(..., description="Reranker score (0.0–1.0)")
    search_score: float = Field(..., description="Raw Qdrant RRF score before reranking")


class RetrievalResult(BaseModel):
    """The reranked top-K chunks for a query plus candidate-count bookkeeping."""

    query: str
    chunks: list[RetrievedChunk]
    total_candidates: int = Field(
        ..., description="How many candidates Qdrant returned before reranking"
    )


class VerificationResult(BaseModel):
    """Verdict on whether retrieved evidence is sufficient to answer."""

    passed: bool
    reason: str = Field(..., description="Human-readable; used verbatim in refusals")
    retrieval: RetrievalResult | None = Field(
        None, description="None only if search itself failed"
    )
    top_score: float = Field(..., description="Best reranker score (0.0 if no results)")
