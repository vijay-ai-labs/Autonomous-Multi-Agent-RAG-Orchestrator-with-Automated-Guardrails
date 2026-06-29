"""Tests for the token-bounded chunker."""

import tiktoken

from ingestion.chunker import MAX_TOKENS, OVERLAP_TOKENS, chunk_document
from ingestion.schemas import Chunk, ParsedDocument, ParsedPage

_enc = tiktoken.get_encoding("cl100k_base")


def _doc(pages: list[ParsedPage]) -> ParsedDocument:
    return ParsedDocument(
        filename="f.bin",
        original_filename="f.pdf",
        doc_type="policy",
        department=None,
        pages=pages,
        page_count=len(pages),
        file_size_bytes=0,
    )


def _long_text(marker: str, sentences: int = 120) -> str:
    """Build text with many distinct sentences (well over 512 tokens)."""
    return " ".join(f"{marker} sentence number {i} about company policy." for i in range(sentences))


def test_returns_list_of_chunks() -> None:
    doc = _doc([ParsedPage(page_number=1, content="A short policy statement.", section="Intro")])
    chunks = chunk_document(doc)
    assert isinstance(chunks, list)
    assert all(isinstance(c, Chunk) for c in chunks)


def test_all_chunks_within_token_limit() -> None:
    doc = _doc([ParsedPage(page_number=1, content=_long_text("alpha"), section="S")])
    chunks = chunk_document(doc)
    assert len(chunks) >= 2
    for c in chunks:
        assert c.token_count <= MAX_TOKENS
        assert len(_enc.encode(c.content)) <= MAX_TOKENS


def test_chunk_index_contiguous_zero_based() -> None:
    doc = _doc(
        [
            ParsedPage(page_number=1, content=_long_text("alpha"), section="S1"),
            ParsedPage(page_number=2, content=_long_text("beta"), section="S2"),
        ]
    )
    chunks = chunk_document(doc)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_overlap_second_chunk_starts_with_tail_of_first() -> None:
    doc = _doc([ParsedPage(page_number=1, content=_long_text("alpha"), section="S")])
    chunks = chunk_document(doc)
    assert len(chunks) >= 2
    first_ids = _enc.encode(chunks[0].content)
    overlap = _enc.decode(first_ids[-OVERLAP_TOKENS:])
    assert chunks[1].content.startswith(overlap)


def test_page_boundary_respected() -> None:
    doc = _doc(
        [
            ParsedPage(page_number=1, content=_long_text("alpha"), section="S1"),
            ParsedPage(page_number=2, content=_long_text("beta"), section="S2"),
        ]
    )
    chunks = chunk_document(doc)
    for c in chunks:
        if c.page_number == 1:
            assert "beta" not in c.content
        elif c.page_number == 2:
            assert "alpha" not in c.content
    # Section metadata follows the source page.
    assert {c.section for c in chunks if c.page_number == 1} == {"S1"}
    assert {c.section for c in chunks if c.page_number == 2} == {"S2"}


def test_single_short_page_produces_one_chunk() -> None:
    doc = _doc([ParsedPage(page_number=1, content="One short sentence here.", section=None)])
    chunks = chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1


def test_char_and_token_counts_match_content() -> None:
    doc = _doc([ParsedPage(page_number=1, content=_long_text("alpha"), section="S")])
    chunks = chunk_document(doc)
    for c in chunks:
        assert c.char_count == len(c.content)
        assert c.token_count == len(_enc.encode(c.content))


def test_empty_page_produces_no_chunks() -> None:
    doc = _doc([ParsedPage(page_number=1, content="", section=None)])
    assert chunk_document(doc) == []
