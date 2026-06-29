"""Tests for the PDF parser."""

from pathlib import Path

from ingestion.parsers.pdf_parser import PDFParser
from ingestion.schemas import ParsedDocument
from tests.conftest import PDF_HEADING


def test_parse_returns_parsed_document(pdf_file: Path, base_metadata: dict) -> None:
    base_metadata["file_size_bytes"] = pdf_file.stat().st_size
    doc = PDFParser().parse(pdf_file, base_metadata)
    assert isinstance(doc, ParsedDocument)


def test_page_count_matches_fixture(pdf_file: Path, base_metadata: dict) -> None:
    doc = PDFParser().parse(pdf_file, base_metadata)
    assert doc.page_count == 2
    assert len(doc.pages) == 2


def test_each_page_has_non_empty_content(pdf_file: Path, base_metadata: dict) -> None:
    doc = PDFParser().parse(pdf_file, base_metadata)
    for page in doc.pages:
        assert page.content.strip() != ""


def test_section_detected_on_all_caps_heading(pdf_file: Path, base_metadata: dict) -> None:
    doc = PDFParser().parse(pdf_file, base_metadata)
    assert doc.pages[0].section == PDF_HEADING


def test_file_size_bytes_recorded(pdf_file: Path, base_metadata: dict) -> None:
    size = pdf_file.stat().st_size
    base_metadata["file_size_bytes"] = size
    doc = PDFParser().parse(pdf_file, base_metadata)
    assert doc.file_size_bytes == size


def test_page_numbers_are_one_indexed(pdf_file: Path, base_metadata: dict) -> None:
    doc = PDFParser().parse(pdf_file, base_metadata)
    assert [p.page_number for p in doc.pages] == [1, 2]


def test_supported_extensions() -> None:
    assert PDFParser().supported_extensions() == [".pdf"]
