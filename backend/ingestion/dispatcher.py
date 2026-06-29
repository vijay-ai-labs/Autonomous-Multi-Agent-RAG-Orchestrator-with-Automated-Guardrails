"""Routing of files to the correct parser and the single Phase 3 entry point."""

import logging
from pathlib import Path

from ingestion.chunker import chunk_document
from ingestion.parsers.base import BaseParser
from ingestion.parsers.docx_parser import DocxParser
from ingestion.parsers.html_parser import HTMLParser
from ingestion.parsers.pdf_parser import PDFParser
from ingestion.schemas import Chunk, ParsedDocument

logger = logging.getLogger(__name__)


def get_parser(filename: str) -> BaseParser:
    """Return the parser for ``filename``'s extension.

    Raises :class:`ValueError` for unsupported extensions.
    """
    ext = Path(filename).suffix.lower()
    parsers: dict[str, BaseParser] = {
        ".pdf": PDFParser(),
        ".docx": DocxParser(),
        ".html": HTMLParser(),
        ".htm": HTMLParser(),
    }
    if ext not in parsers:
        raise ValueError(f"Unsupported file type: {ext}. Allowed: {list(parsers)}")
    return parsers[ext]


def parse_and_chunk(
    file_path: Path,
    metadata: dict,
) -> tuple[ParsedDocument, list[Chunk]]:
    """Parse a file and chunk it. Single entry point for the Phase 3 worker."""
    parser = get_parser(metadata["original_filename"])
    parsed = parser.parse(file_path, metadata)
    chunks = chunk_document(parsed)
    logger.info(
        "Parsed %s: %d page(s), %d chunk(s)",
        metadata["original_filename"],
        parsed.page_count,
        len(chunks),
    )
    return parsed, chunks
