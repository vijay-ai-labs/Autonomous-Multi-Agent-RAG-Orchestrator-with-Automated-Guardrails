"""HTML parser built on BeautifulSoup (>= 4.12) with the lxml backend.

Targets Confluence and Notion page exports: strips navigation/chrome, then streams
headings and body text in document order, grouping into ~3000-char synthetic pages.
"""

import logging
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from ingestion.parsers.base import BaseParser, clean_whitespace, group_into_pages
from ingestion.schemas import ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)

# Same heading sentinel approach as the DOCX parser.
_HEADING_MARK = "\x00HEADING\x00"

_STRIP_TAGS = ("nav", "header", "footer", "script", "style")
_STRIP_SELECTORS = (
    ".page-sidebar",
    ".breadcrumb",
    "#footer",
    ".page-metadata",
    '[role="navigation"]',
)

_HEADING_TAGS = {"h1", "h2", "h3"}
_TEXT_TAGS = {"p", "td", "th", "li"}
_CONTENT_TAGS = _HEADING_TAGS | _TEXT_TAGS


class HTMLParser(BaseParser):
    """Strip chrome, then extract headings and body text from an HTML export."""

    def supported_extensions(self) -> list[str]:
        return [".html", ".htm"]

    def parse(self, file_path: Path, metadata: dict) -> ParsedDocument:
        html = file_path.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")

        for tag_name in _STRIP_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()
        for selector in _STRIP_SELECTORS:
            for element in soup.select(selector):
                element.decompose()

        root = soup.body or soup
        lines: list[str] = []
        for element in root.find_all(list(_CONTENT_TAGS)):
            if not isinstance(element, Tag):
                continue
            text = element.get_text(separator=" ", strip=True)
            if not text:
                continue
            if element.name in _HEADING_TAGS:
                lines.append(f"{_HEADING_MARK}{text}")
            elif element.name == "li":
                lines.append(f"• {text}")
            else:
                lines.append(text)

        stream = "\n".join(lines)
        groups = group_into_pages(stream)

        pages: list[ParsedPage] = []
        last_section: str | None = None
        for index, group in enumerate(groups, start=1):
            page_section = last_section
            cleaned_lines: list[str] = []
            for line in group.split("\n"):
                if line.startswith(_HEADING_MARK):
                    heading = line[len(_HEADING_MARK):].strip()
                    last_section = heading
                    if page_section is None:
                        page_section = heading
                    cleaned_lines.append(heading)
                else:
                    cleaned_lines.append(line)
            content = clean_whitespace("\n".join(cleaned_lines))
            pages.append(
                ParsedPage(page_number=index, content=content, section=page_section)
            )

        return ParsedDocument(
            filename=metadata["filename"],
            original_filename=metadata["original_filename"],
            doc_type=metadata["doc_type"],
            department=metadata.get("department"),
            pages=pages,
            page_count=len(pages),
            file_size_bytes=metadata["file_size_bytes"],
        )
