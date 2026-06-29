"""File-format parsers that turn raw documents into :class:`ParsedDocument`."""

from ingestion.parsers.base import BaseParser
from ingestion.parsers.docx_parser import DocxParser
from ingestion.parsers.html_parser import HTMLParser
from ingestion.parsers.pdf_parser import PDFParser

__all__ = ["BaseParser", "PDFParser", "DocxParser", "HTMLParser"]
