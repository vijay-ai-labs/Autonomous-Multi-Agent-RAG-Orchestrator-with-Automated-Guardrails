"""Tests for the Qdrant hybrid searcher with the client fully mocked."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.models import Fusion, FusionQuery
from uuid import uuid4

from core.access import UserScope
from retrieval.searcher import hybrid_search

_ADMIN = UserScope(id=uuid4(), role="admin", departments=())
_EMPLOYEE = UserScope(id=uuid4(), role="employee", departments=("hr",))


def _fake_hit(chunk_index: int) -> MagicMock:
    return MagicMock(
        score=0.9 - chunk_index * 0.1,
        payload={
            "content": f"content {chunk_index}",
            "chunk_index": chunk_index,
            "page_number": chunk_index + 1,
            "section": f"section {chunk_index}",
            "filename": "handbook.pdf",
            "doc_type": "policy",
            "department": "hr",
            "document_id": "doc-123",
        },
    )


@pytest.fixture
def query_points_mock(monkeypatch):
    """Patch ``client.query_points`` to return three fake hits."""
    mock = AsyncMock(return_value=MagicMock(points=[_fake_hit(i) for i in range(3)]))
    monkeypatch.setattr("retrieval.searcher.client.query_points", mock)
    return mock


_DENSE = [0.1] * 1536
_SPARSE_IDX = [1, 2, 3]
_SPARSE_VAL = [0.5, 0.3, 0.2]


@pytest.mark.asyncio
async def test_returns_list_of_payload_dicts(query_points_mock):
    results = await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN)

    assert len(results) == 3
    first = results[0]
    assert first["content"] == "content 0"
    assert first["search_score"] == pytest.approx(0.9)
    assert set(first) == {
        "content",
        "chunk_index",
        "page_number",
        "section",
        "filename",
        "doc_type",
        "department",
        "document_id",
        "search_score",
    }


@pytest.mark.asyncio
async def test_query_points_called_with_collection_and_rrf_fusion(query_points_mock):
    from core.config import get_settings

    await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN)

    kwargs = query_points_mock.call_args.kwargs
    assert kwargs["collection_name"] == get_settings().QDRANT_COLLECTION
    assert isinstance(kwargs["query"], FusionQuery)
    assert kwargs["query"].fusion == Fusion.RRF


@pytest.mark.asyncio
async def test_two_prefetches_dense_and_sparse(query_points_mock):
    await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN)

    prefetch = query_points_mock.call_args.kwargs["prefetch"]
    assert len(prefetch) == 2
    usings = {p.using for p in prefetch}
    assert usings == {"", "bm25"}


@pytest.mark.asyncio
async def test_filter_always_pins_status_active(query_points_mock):
    await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN)

    must = query_points_mock.call_args.kwargs["prefetch"][0].filter.must
    assert len(must) == 1
    assert must[0].key == "status"
    assert must[0].match.value == "active"


@pytest.mark.asyncio
async def test_doc_type_adds_second_filter_condition(query_points_mock):
    await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN, doc_type="hr")

    must = query_points_mock.call_args.kwargs["prefetch"][0].filter.must
    keys = {c.key: c.match.value for c in must}
    assert len(must) == 2
    assert keys == {"status": "active", "doc_type": "hr"}


@pytest.mark.asyncio
async def test_admin_has_no_rbac_clause(query_points_mock):
    """Admin filter is status-only — no department restriction."""
    await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN)

    must = query_points_mock.call_args.kwargs["prefetch"][0].filter.must
    assert all(getattr(c, "key", None) != "department" for c in must)
    assert all(getattr(c, "should", None) is None for c in must)


@pytest.mark.asyncio
async def test_non_admin_adds_department_or_shared_clause(query_points_mock):
    """Employee filter restricts to own departments OR shared (null) docs."""
    await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_EMPLOYEE)

    must = query_points_mock.call_args.kwargs["prefetch"][0].filter.must
    # status pin + nested RBAC Filter
    assert any(getattr(c, "key", None) == "status" for c in must)
    rbac = next(c for c in must if getattr(c, "should", None) is not None)
    # One branch matches the allowed departments, one matches null (shared).
    has_dept_match = any(
        getattr(s, "key", None) == "department"
        and getattr(getattr(s, "match", None), "any", None) == ["hr"]
        for s in rbac.should
    )
    has_null_branch = any(getattr(s, "is_null", None) is not None for s in rbac.should)
    assert has_dept_match
    assert has_null_branch


@pytest.mark.asyncio
async def test_empty_result_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        "retrieval.searcher.client.query_points",
        AsyncMock(return_value=MagicMock(points=[])),
    )
    assert await hybrid_search(_DENSE, _SPARSE_IDX, _SPARSE_VAL, scope=_ADMIN) == []
