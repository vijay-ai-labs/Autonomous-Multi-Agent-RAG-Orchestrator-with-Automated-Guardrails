"""Pydantic v2 data contracts shared by parsers, chunker, and the Phase 3 worker.

A parser produces a :class:`ParsedDocument` (a list of :class:`ParsedPage`); the
chunker consumes it and produces a list of :class:`Chunk`.
"""

from pydantic import BaseModel, Field


class ParsedPage(BaseModel):
    """A single logical page of a parsed document."""

    page_number: int = Field(..., description="1-indexed page number")
    content: str = Field(..., description="Raw text of this page (\"\" if empty/image-only)")
    section: str | None = Field(None, description="Heading text if detectable, else None")


class ParsedDocument(BaseModel):
    """A fully parsed document, prior to chunking."""

    filename: str = Field(..., description="Stored filename (UUID-based)")
    original_filename: str = Field(..., description="User-uploaded filename")
    doc_type: str = Field(..., description="policy | hr | it | sop | compliance | faq")
    department: str | None = None
    pages: list[ParsedPage]
    page_count: int
    file_size_bytes: int


class Chunk(BaseModel):
    """A token-bounded segment of a document, ready for embedding in Phase 3."""

    chunk_index: int = Field(..., description="0-indexed position across the whole document")
    content: str = Field(..., description="Chunk text (<= 512 tokens)")
    page_number: int | None = Field(None, description="Page where this chunk starts")
    section: str | None = Field(None, description="Section heading where this chunk starts")
    char_count: int = Field(..., description="len(content)")
    token_count: int = Field(..., description="Approximate token count (cl100k_base)")
