"""Top-level retrieval pipeline — the single entry point for SP2 Phase 2.

Orchestrates: embed query → hybrid search → rerank → verify. Callers check
``VerificationResult.passed`` before generating an answer. Keep this interface
stable; it is the only module SP2 Phase 2 imports from the retrieval package.
"""

import logging

from core.access import UserScope
from core.config import get_settings
from retrieval.query_embedder import embed_query
from retrieval.reranker import rerank
from retrieval.schemas import RetrievalResult, RetrievedChunk, VerificationResult
from retrieval.searcher import hybrid_search
from retrieval.verifier import verify_evidence

logger = logging.getLogger(__name__)


async def retrieve(
    query: str,
    scope: UserScope,
    doc_type: str | None = None,
    department: str | None = None,
) -> VerificationResult:
    """Run the full retrieval pipeline and return an evidence verdict.

    1. Embed the query (dense + sparse).
    2. Hybrid search Qdrant with RRF fusion (filtered to active docs the
       caller's ``scope`` is allowed to read).
    3. Rerank candidates with FlashRank.
    4. Verify evidence sufficiency.

    Check ``.passed`` before generating an answer.
    """
    settings = get_settings()
    top_k = settings.MAX_CHUNKS_PER_QUERY

    dense, sparse_idx, sparse_val = await embed_query(query)
    candidates = await hybrid_search(
        dense_vector=dense,
        sparse_indices=sparse_idx,
        sparse_values=sparse_val,
        scope=scope,
        doc_type=doc_type,
        department=department,
    )
    reranked = await rerank(query=query, candidates=candidates, top_k=top_k)

    chunks = [
        RetrievedChunk(
            chunk_index=c["chunk_index"],
            content=c["content"],
            page_number=c.get("page_number"),
            section=c.get("section"),
            filename=c["filename"],
            doc_type=c["doc_type"],
            department=c.get("department"),
            document_id=c["document_id"],
            score=c["score"],
            search_score=c["search_score"],
        )
        for c in reranked
    ]
    retrieval_result = RetrievalResult(
        query=query,
        chunks=chunks,
        total_candidates=len(candidates),
    )
    return verify_evidence(retrieval_result)
