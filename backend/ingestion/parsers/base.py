"""Abstract base class for parsers plus shared text-normalisation helpers."""

import re
from abc import ABC, abstractmethod
from pathlib import Path

from ingestion.schemas import ParsedDocument

# Pages grouped to roughly this many characters for formats without real pages
# (DOCX, HTML). Tuned so a group lands well under the 512-token chunk window.
PAGE_CHAR_TARGET = 3000

# A heading candidate must be shorter than this to count as a heading.
HEADING_MAX_LEN = 80

# Below this many characters a page is treated as empty (likely image-only).
MIN_PAGE_CHARS = 20

_THREE_PLUS_NEWLINES = re.compile(r"\n{3,}")


def clean_whitespace(text: str) -> str:
    """Collapse 3+ consecutive newlines to 2 and strip leading/trailing whitespace.

    Trailing spaces on individual lines are also removed so heading detection and
    chunking operate on normalised text.
    """
    if not text:
        return ""
    # Normalise line endings, then drop trailing spaces on each line.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _THREE_PLUS_NEWLINES.sub("\n\n", text)
    return text.strip()


def group_into_pages(text: str, target_chars: int = PAGE_CHAR_TARGET) -> list[str]:
    """Split a flat text stream into groups of roughly ``target_chars`` characters.

    Splits on newline boundaries so paragraphs are not cut mid-line. Always returns
    at least one group (possibly empty) so callers get a deterministic page count.
    """
    lines = text.split("\n")
    groups: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        # +1 accounts for the newline that rejoins lines.
        if current and current_len + len(line) + 1 > target_chars:
            groups.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        groups.append("\n".join(current))
    return groups or [""]


class BaseParser(ABC):
    """Contract every format parser implements."""

    @abstractmethod
    def parse(self, file_path: Path, metadata: dict) -> ParsedDocument:
        """Parse the file at ``file_path``.

        ``metadata`` contains: ``filename``, ``original_filename``, ``doc_type``,
        ``department``, ``file_size_bytes``.
        """
        ...

    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return the lower-cased extensions (with leading dot) this parser handles."""
        ...
