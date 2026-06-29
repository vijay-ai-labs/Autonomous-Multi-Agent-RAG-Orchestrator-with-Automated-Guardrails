"""Token-bounded chunking of a :class:`ParsedDocument`.

Chunks are at most ``MAX_TOKENS`` tokens (cl100k_base, the GPT-4o tokenizer) with an
``OVERLAP_TOKENS``-token rolling overlap. Chunking resets at every page boundary, so a
chunk never spans two pages. Within a page, splits prefer sentence/newline boundaries
and only fall back to a hard token split when a single sentence exceeds the window.
"""

import logging
import re

import tiktoken

from ingestion.schemas import Chunk, ParsedDocument

logger = logging.getLogger(__name__)

MAX_TOKENS = 512
OVERLAP_TOKENS = 50
# Small safety margin: assembling overlap + body and re-encoding can shift token
# boundaries by a token or two. Reserving a few tokens keeps every chunk <= MAX_TOKENS.
_BOUNDARY_MARGIN = 4

_ENCODING_NAME = "cl100k_base"
_encoding = tiktoken.get_encoding(_ENCODING_NAME)

# Split after a period+whitespace, or on one-or-more newlines.
_SENTENCE_SPLIT = re.compile(r"(?<=\.)\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    """Split page text into sentence-ish segments, dropping empties."""
    return [seg.strip() for seg in _SENTENCE_SPLIT.split(text) if seg.strip()]


def _token_len(text: str) -> int:
    return len(_encoding.encode(text))


def _chunk_page(
    content: str,
    page_number: int,
    section: str | None,
    start_index: int,
) -> list[Chunk]:
    """Produce the ordered chunks for a single page, indexed from ``start_index``."""
    segments = _split_sentences(content)
    if not segments:
        return []

    chunks: list[Chunk] = []
    prev_full_ids: list[int] = []
    pos = 0
    next_index = start_index

    while pos < len(segments):
        is_first = not chunks
        if is_first:
            overlap_prefix = ""
            budget = MAX_TOKENS
        else:
            overlap_ids = prev_full_ids[-OVERLAP_TOKENS:]
            overlap_prefix = _encoding.decode(overlap_ids)
            budget = MAX_TOKENS - len(overlap_ids) - _BOUNDARY_MARGIN

        body_parts: list[str] = []
        body_tokens = 0
        while pos < len(segments):
            seg = segments[pos]
            seg_tokens = _token_len(seg)
            if seg_tokens > budget and not body_parts:
                # Single segment larger than the window: hard-split on tokens and
                # push the remainder back so it starts the next chunk.
                seg_ids = _encoding.encode(seg)
                head = _encoding.decode(seg_ids[:budget])
                remainder = _encoding.decode(seg_ids[budget:])
                body_parts.append(head)
                body_tokens += budget
                segments[pos] = remainder
                break
            if body_tokens + seg_tokens <= budget:
                body_parts.append(seg)
                body_tokens += seg_tokens
                pos += 1
            else:
                break

        body = " ".join(body_parts)
        text = f"{overlap_prefix} {body}".strip() if overlap_prefix else body

        # Guarantee the hard ceiling even if boundary effects pushed us over.
        ids = _encoding.encode(text)
        if len(ids) > MAX_TOKENS:
            text = _encoding.decode(ids[:MAX_TOKENS])
            ids = _encoding.encode(text)

        if not text.strip():
            logger.warning("Skipping whitespace-only chunk on page %d", page_number)
            continue

        chunks.append(
            Chunk(
                chunk_index=next_index,
                content=text,
                page_number=page_number,
                section=section,
                char_count=len(text),
                token_count=len(ids),
            )
        )
        next_index += 1
        prev_full_ids = ids

    return chunks


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """Chunk a :class:`ParsedDocument` into overlapping token-bounded segments."""
    chunks: list[Chunk] = []
    for page in doc.pages:
        if not page.content.strip():
            logger.debug("Page %d of %s is empty; no chunks", page.page_number, doc.filename)
            continue
        page_chunks = _chunk_page(
            content=page.content,
            page_number=page.page_number,
            section=page.section,
            start_index=len(chunks),
        )
        chunks.extend(page_chunks)
    return chunks
