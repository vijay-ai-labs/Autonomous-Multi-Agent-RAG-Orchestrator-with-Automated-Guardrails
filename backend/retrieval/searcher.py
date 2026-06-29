"""Qdrant hybrid search: dense + sparse prefetch fused with RRF.

Runs two prefetches (dense over the unnamed default vector, sparse over the
``bm25`` named vector) and fuses them server-side with Reciprocal Rank Fusion.
A ``status="active"`` filter is always applied. For non-admin callers an RBAC
clause restricts results to the caller's ``departments`` plus shared docs
(``department`` null); admins are unrestricted. ``doc_type`` and ``department``
narrow further when provided. All fields are payload-indexed keywords, so
filtering is cheap.
"""

import logging

from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    IsNullCondition,
    MatchAny,
    MatchValue,
    PayloadField,
    Prefetch,
    SparseVector,
)

from core.access import UserScope
from core.config import get_settings
from core.qdrant import SPARSE_VECTOR_NAME, client

logger = logging.getLogger(__name__)

_DENSE_VECTOR_NAME = ""  # unnamed default dense vector slot in the collection


def _build_filter(
    scope: UserScope, doc_type: str | None, department: str | None
) -> Filter:
    """Build the metadata filter; always pins ``status="active"``.

    Non-admin callers get an RBAC clause: ``department`` in their allowed set
    OR ``department`` is null (shared/company-wide docs). Admins skip the clause.
    """
    conditions = [FieldCondition(key="status", match=MatchValue(value="active"))]

    if not scope.is_admin:
        rbac_should: list = [
            IsNullCondition(is_null=PayloadField(key="department"))
        ]
        if scope.departments:
            rbac_should.append(
                FieldCondition(
                    key="department", match=MatchAny(any=list(scope.departments))
                )
            )
        conditions.append(Filter(should=rbac_should))

    if doc_type is not None:
        conditions.append(
            FieldCondition(key="doc_type", match=MatchValue(value=doc_type))
        )
    if department is not None:
        conditions.append(
            FieldCondition(key="department", match=MatchValue(value=department))
        )
    return Filter(must=conditions)


async def hybrid_search(
    dense_vector: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    scope: UserScope,
    doc_type: str | None = None,
    department: str | None = None,
    prefetch_limit: int = 50,
    fusion_limit: int = 20,
) -> list[dict]:
    """Run RRF-fused dense+sparse search and return hit payloads with scores.

    Results are restricted to documents ``scope`` is allowed to read. Returns a
    list of dicts (one per hit). Returns an empty list when Qdrant matches
    nothing — never raises on an empty result.
    """
    settings = get_settings()
    search_filter = _build_filter(scope, doc_type, department)

    dense_prefetch = Prefetch(
        query=dense_vector,
        using=_DENSE_VECTOR_NAME,
        limit=prefetch_limit,
        filter=search_filter,
    )
    sparse_prefetch = Prefetch(
        query=SparseVector(indices=sparse_indices, values=sparse_values),
        using=SPARSE_VECTOR_NAME,
        limit=prefetch_limit,
        filter=search_filter,
    )

    results = await client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        prefetch=[dense_prefetch, sparse_prefetch],
        query=FusionQuery(fusion=Fusion.RRF),
        limit=fusion_limit,
        with_payload=True,
        with_vectors=False,
    )

    candidates = [
        {
            "content": hit.payload["content"],
            "chunk_index": hit.payload["chunk_index"],
            "page_number": hit.payload.get("page_number"),
            "section": hit.payload.get("section"),
            "filename": hit.payload["filename"],
            "doc_type": hit.payload["doc_type"],
            "department": hit.payload.get("department"),
            "document_id": hit.payload["document_id"],
            "search_score": hit.score,
        }
        for hit in results.points
    ]
    logger.info(
        "Hybrid search returned %d candidates (doc_type=%s)",
        len(candidates),
        doc_type,
    )
    return candidates
