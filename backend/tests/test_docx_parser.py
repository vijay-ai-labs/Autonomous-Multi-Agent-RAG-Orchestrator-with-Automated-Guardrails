"""Tests for the DOCX parser."""

from pathlib import Path

from ingestion.parsers.docx_parser import DocxParser
from ingestion.schemas import ParsedDocument
from tests.conftest import DOCX_HEADING_1, DOCX_HEADING_2


def test_parse_returns_parsed_document(docx_file: Path, base_metadata: dict) -> None:
    doc = DocxParser().parse(docx_file, base_metadata)
    assert isinstance(doc, ParsedDocument)
    assert doc.page_count == len(doc.pages)
    assert doc.page_count >= 1


def _all_text(doc: ParsedDocument) -> str:
    return "\n".join(p.content for p in doc.pages)


def test_headings_extracted_as_sections(docx_file: Path, base_metadata: dict) -> None:
    doc = DocxParser().parse(docx_file, base_metadata)
    sections = {p.section for p in doc.pages}
    # The small fixture fits in a single ~3000-char group, so the page's section is
    # the first heading; both headings must appear in the body text regardless.
    assert DOCX_HEADING_1 in sections
    text = _all_text(doc)
    assert DOCX_HEADING_1 in text
    assert DOCX_HEADING_2 in text


def test_table_cells_extracted(docx_file: Path, base_metadata: dict) -> None:
    doc = DocxParser().parse(docx_file, base_metadata)
    text = _all_text(doc)
    # Rows are rendered as "cell | cell".
    assert "Asset | Owner" in text
    assert "Laptop | IT" in text


def test_empty_paragraphs_skipped(docx_file: Path, base_metadata: dict) -> None:
    doc = DocxParser().parse(docx_file, base_metadata)
    for page in doc.pages:
        assert "\n\n\n" not in page.content
        for line in page.content.split("\n"):
            # No purely empty lines should survive from skipped paragraphs except
            # the single blank line allowed between blocks.
            assert line == "" or line.strip() != ""


def test_supported_extensions() -> None:
    assert DocxParser().supported_extensions() == [".docx"]
