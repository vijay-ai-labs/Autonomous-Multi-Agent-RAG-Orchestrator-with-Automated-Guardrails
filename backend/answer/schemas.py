"""Pydantic request/response models for the query API and pipeline."""

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A single source reference matching an inline ``[Source N]`` marker."""

    source_num: int  # 1-indexed, matches [Source N] in answer text
    filename: str  # original_filename from retrieved chunk
    page_number: int | None
    section: str | None
    excerpt: str  # chunk.content[:300] — preview of source evidence
    document_id: str


class QueryRequest(BaseModel):
    """Inbound query payload for POST /api/query."""

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None  # None → new session generated server-side
    doc_type: str | None = None
    department: str | None = None


class QueryResponse(BaseModel):
    """Grounded answer (or refusal) returned to the client."""

    query_id: str
    session_id: str
    answer: str  # may contain [Source N] inline citations
    citations: list[Citation]  # ordered by source_num
    confidence: float  # top reranker score from verification
    refused: bool = False
    refusal_reason: str | None = None  # populated when refused=True


class RefusalResponse(BaseModel):
    """Structured refusal built when verification fails."""

    query_id: str
    session_id: str
    refused: bool = True
    refusal_reason: str
    answer: str  # user-facing message (from refusal.py)
    citations: list[Citation] = []
    confidence: float = 0.0
