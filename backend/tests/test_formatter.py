"""Tests for the citation formatter."""

from answer.formatter import format_context
from answer.schemas import Citation
from retrieval.schemas import RetrievedChunk


def _chunk(idx: int, page, section, content) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_index=idx,
        content=content,
        page_number=page,
        section=section,
        filename=f"f{idx}.pdf",
        doc_type="policy",
        department="hr",
        document_id=f"doc-{idx}",
        score=0.9,
        search_score=0.5,
    )


def _chunks() -> list[RetrievedChunk]:
    return [
        _chunk(1, 12, "Vacation Policy", "Employees get 20 days." * 20),
        _chunk(2, None, "Benefits", "Health benefits info."),
        _chunk(3, 3, None, "Equipment policy text."),
    ]


def test_returns_str_and_citation_list():
    context_block, citations = format_context(_chunks())
    assert isinstance(context_block, str)
    assert isinstance(citations, list)
    assert all(isinstance(c, Citation) for c in citations)


def test_context_contains_all_source_markers():
    context_block, _ = format_context(_chunks())
    assert "[Source 1]" in context_block
    assert "[Source 2]" in context_block
    assert "[Source 3]" in context_block


def test_context_contains_filename_and_content():
    chunks = _chunks()
    context_block, _ = format_context(chunks)
    for chunk in chunks:
        assert chunk.filename in context_block
        assert chunk.content in context_block


def test_citations_indexed_one_based():
    _, citations = format_context(_chunks())
    assert len(citations) == 3
    assert [c.source_num for c in citations] == [1, 2, 3]


def test_excerpt_truncated_to_300_chars():
    _, citations = format_context(_chunks())
    assert citations[0].excerpt == ("Employees get 20 days." * 20)[:300]
    assert len(citations[0].excerpt) == 300


def test_section_none_omits_section_field():
    context_block, _ = format_context(_chunks())
    # Source 3 has section=None → header ends after Page, no "| Section:"
    assert "[Source 3] Document: f3.pdf | Page: 3" in context_block
    assert "[Source 3] Document: f3.pdf | Page: 3 | Section:" not in context_block


def test_page_none_omits_page_field():
    context_block, _ = format_context(_chunks())
    # Source 2 has page_number=None → no "| Page:" in its header
    assert "[Source 2] Document: f2.pdf | Section: Benefits" in context_block
    assert "[Source 2] Document: f2.pdf | Page:" not in context_block
