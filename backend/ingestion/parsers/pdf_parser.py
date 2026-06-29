"""PDF parser built on pypdf (>= 4.0)."""

import logging
from pathlib import Path

from pypdf import PdfReader

from ingestion.parsers.base import (
    HEADING_MAX_LEN,
    MIN_PAGE_CHARS,
    BaseParser,
    clean_whitespace,
)
from ingestion.schemas import ParsedDocument, ParsedPage

logger = logging.getLogger(__name__)


def _is_heading(line: str) -> bool:
    """A line is a heading if it is short and either ALL CAPS or ends with a colon."""
    stripped = line.strip()
    if not stripped or len(stripped) >= HEADING_MAX_LEN:
        return False
    if stripped.endswith(":"):
        return True
    # ALL CAPS: has at least one letter and no lowercase letters.
    return any(c.isalpha() for c in stripped) and stripped.upper() == stripped


def _detect_section(content: str) -> str | None:
    """Return the first heading at page start or immediately after a blank line."""
    lines = content.split("\n")
    prev_blank = True  # the first line counts as "page start"
    for line in lines:
        if line.strip() == "":
            prev_blank = True
            continue
        if prev_blank and _is_heading(line):
            return line.strip()
        prev_blank = False
    return None


class PDFParser(BaseParser):
    """Extract text page-by-page from a PDF, detecting per-page section headings."""

    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    def parse(self, file_path: Path, metadata: dict) -> ParsedDocument:
        reader = PdfReader(str(file_path))
        page_count = len(reader.pages)
        pages: list[ParsedPage] = []

        for index, page in enumerate(reader.pages, start=1):
            try:
                raw = page.extract_text() or ""
            except Exception:  # pragma: no cover - defensive; pypdf can raise on odd pages
                logger.warning("Failed to extract text from page %d of %s", index, file_path.name)
                raw = ""

            content = clean_whitespace(raw)
            section = _detect_section(content) if content else None

            if len(content) < MIN_PAGE_CHARS:
                if content:
                    logger.warning(
                        "Page %d of %s has < %d chars; treating as empty (image-only?)",
                        index,
                        file_path.name,
                        MIN_PAGE_CHARS,
                    )
                content = ""
                section = None

            pages.append(ParsedPage(page_number=index, content=content, section=section))

        return ParsedDocument(
            filename=metadata["filename"],
            original_filename=metadata["original_filename"],
            doc_type=metadata["doc_type"],
            department=metadata.get("department"),
            pages=pages,
            page_count=page_count,
            file_size_bytes=metadata["file_size_bytes"],
        )
