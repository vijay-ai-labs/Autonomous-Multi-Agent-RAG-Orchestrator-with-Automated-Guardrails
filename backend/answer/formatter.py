"""Convert reranked chunks into a prompt context block and citation list."""

from answer.schemas import Citation
from retrieval.schemas import RetrievedChunk


def format_context(chunks: list[RetrievedChunk]) -> tuple[str, list[Citation]]:
    """Build the GPT-4o context block and the client-facing citation list.

    Context block format (one entry per chunk)::

        ---
        [Source 1] Document: employee-handbook.pdf | Page: 12 | Section: Vacation Policy
        <chunk content>
        ---

    Citations list: one Citation per chunk, 1-indexed source_num,
    ``excerpt = chunk.content[:300]``.
    """
    context_parts: list[str] = []
    citations: list[Citation] = []

    for i, chunk in enumerate(chunks, start=1):
        header = f"[Source {i}] Document: {chunk.filename}"
        if chunk.page_number is not None:
            header += f" | Page: {chunk.page_number}"
        if chunk.section:
            header += f" | Section: {chunk.section}"
        context_parts.append(f"---\n{header}\n{chunk.content}\n---")
        citations.append(
            Citation(
                source_num=i,
                filename=chunk.filename,
                page_number=chunk.page_number,
                section=chunk.section,
                excerpt=chunk.content[:300],
                document_id=chunk.document_id,
            )
        )

    context_block = "\n".join(context_parts)
    return context_block, citations
