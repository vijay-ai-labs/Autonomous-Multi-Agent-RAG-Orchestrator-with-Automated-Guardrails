"""Tests for the HTML parser."""

from pathlib import Path

from ingestion.parsers.html_parser import HTMLParser
from ingestion.schemas import ParsedDocument
from tests.conftest import HTML_SECTION_A, HTML_SECTION_B


def _all_text(doc: ParsedDocument) -> str:
    return "\n".join(p.content for p in doc.pages)


def test_parse_returns_parsed_document(html_file: Path, base_metadata: dict) -> None:
    doc = HTMLParser().parse(html_file, base_metadata)
    assert isinstance(doc, ParsedDocument)
    assert doc.page_count == len(doc.pages)


def test_nav_footer_script_style_stripped(html_file: Path, base_metadata: dict) -> None:
    doc = HTMLParser().parse(html_file, base_metadata)
    text = _all_text(doc)
    for marker in (
        "SHOULD_NOT_APPEAR_NAV",
        "SHOULD_NOT_APPEAR_HEADER",
        "SHOULD_NOT_APPEAR_FOOTER",
        "SHOULD_NOT_APPEAR_BREADCRUMB",
        "SHOULD_NOT_APPEAR_ROLE_NAV",
        "should-not-appear",
    ):
        assert marker not in text


def test_confluence_metadata_div_stripped(html_file: Path, base_metadata: dict) -> None:
    doc = HTMLParser().parse(html_file, base_metadata)
    assert "SHOULD_NOT_APPEAR_META" not in _all_text(doc)


def test_h2_headings_become_sections(html_file: Path, base_metadata: dict) -> None:
    doc = HTMLParser().parse(html_file, base_metadata)
    text = _all_text(doc)
    assert HTML_SECTION_A in text
    assert HTML_SECTION_B in text
    sections = {p.section for p in doc.pages}
    assert HTML_SECTION_A in sections


def test_list_items_have_bullet_prefix(html_file: Path, base_metadata: dict) -> None:
    doc = HTMLParser().parse(html_file, base_metadata)
    text = _all_text(doc)
    assert "• Request an account from IT" in text
    assert "• Read the security policy" in text


def test_supported_extensions() -> None:
    assert HTMLParser().supported_extensions() == [".html", ".htm"]
