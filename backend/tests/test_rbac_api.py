"""Integration tests for RBAC enforcement across the query/ingest/documents routes.

The pipeline, Celery enqueue, Redis, and DB session are mocked; only the
access-control decisions are exercised. Scope is injected via the ``patch_scope``
fixture (see conftest), which leaves the bearer-token check intact.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from answer.schemas import QueryResponse


def _answer() -> QueryResponse:
    return QueryResponse(
        query_id="q-1", session_id="s-1", answer="ok [Source 1].",
        citations=[], confidence=0.8, refused=False,
    )


# ── query route ───────────────────────────────────────────────────────────


@pytest.fixture
def query_client(fake_db, monkeypatch, patch_scope):
    from api.main import app
    from core.database import get_session
    import api.routes.query as query_mod

    app.dependency_overrides[get_session] = lambda: fake_db
    pipeline_mock = AsyncMock(return_value=_answer())
    monkeypatch.setattr(query_mod, "run_query_pipeline", pipeline_mock)

    yield TestClient(app), pipeline_mock, patch_scope
    app.dependency_overrides.clear()


def test_query_out_of_scope_department_is_forbidden(query_client, auth_headers):
    client, pipeline_mock, set_scope = query_client
    set_scope("employee", ("hr",))

    resp = client.post(
        "/api/query",
        json={"query": "salary bands?", "department": "finance"},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    pipeline_mock.assert_not_called()  # rejected before retrieval


def test_query_in_scope_department_passes_scope_to_pipeline(query_client, auth_headers):
    client, pipeline_mock, set_scope = query_client
    set_scope("employee", ("hr",))

    resp = client.post(
        "/api/query",
        json={"query": "leave policy?", "department": "hr"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    kwargs = pipeline_mock.call_args.kwargs
    assert kwargs["department"] == "hr"
    assert kwargs["user_role"] == "employee"
    assert kwargs["user_departments"] == ["hr"]


def test_query_no_department_uses_full_scope(query_client, auth_headers):
    client, pipeline_mock, set_scope = query_client
    set_scope("employee", ("hr",))

    resp = client.post("/api/query", json={"query": "hi"}, headers=auth_headers)
    assert resp.status_code == 200
    assert pipeline_mock.call_args.kwargs["department"] is None


# ── ingest route ────────────────────────────────────────────────────────────


@pytest.fixture
def ingest_client(fake_db, monkeypatch, patch_scope):
    from api.main import app
    from core.database import get_session
    import api.routes.ingest as ingest_mod

    app.dependency_overrides[get_session] = lambda: fake_db
    monkeypatch.setattr(
        ingest_mod.ingest_document, "delay",
        lambda *a, **k: SimpleNamespace(id="job-1"),
    )
    monkeypatch.setattr(ingest_mod, "redis_client", AsyncMock())

    yield TestClient(app), patch_scope
    app.dependency_overrides.clear()


def _pdf_upload(pdf_file):
    return {"file": ("sample.pdf", pdf_file.read_bytes(), "application/pdf")}


def test_ingest_shared_doc_forbidden_for_employee(ingest_client, pdf_file, auth_headers):
    client, set_scope = ingest_client
    set_scope("employee", ("hr",))
    resp = client.post(
        "/api/ingest", files=_pdf_upload(pdf_file),
        data={"doc_type": "policy"},  # no department → shared
        headers=auth_headers,
    )
    assert resp.status_code == 403


def test_ingest_other_department_forbidden_for_employee(ingest_client, pdf_file, auth_headers):
    client, set_scope = ingest_client
    set_scope("employee", ("hr",))
    resp = client.post(
        "/api/ingest", files=_pdf_upload(pdf_file),
        data={"doc_type": "policy", "department": "finance"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


def test_ingest_own_department_allowed_for_employee(ingest_client, pdf_file, auth_headers):
    client, set_scope = ingest_client
    set_scope("employee", ("hr",))
    resp = client.post(
        "/api/ingest", files=_pdf_upload(pdf_file),
        data={"doc_type": "policy", "department": "hr"},
        headers=auth_headers,
    )
    assert resp.status_code == 202


# ── documents route ──────────────────────────────────────────────────────────


@pytest.fixture
def documents_client(fake_db, monkeypatch, patch_scope):
    from api.main import app
    from core.database import get_session

    app.dependency_overrides[get_session] = lambda: fake_db
    yield TestClient(app), fake_db, patch_scope
    app.dependency_overrides.clear()


def test_documents_list_out_of_scope_filter_forbidden(documents_client, auth_headers):
    client, _, set_scope = documents_client
    set_scope("employee", ("hr",))
    resp = client.get("/api/documents?department=finance", headers=auth_headers)
    assert resp.status_code == 403


def test_documents_delete_other_department_forbidden(documents_client, auth_headers):
    client, fake_db, set_scope = documents_client
    set_scope("employee", ("hr",))

    from models.tables import Document

    async def _get(model, pk):
        return Document(
            filename="f", original_filename="f.pdf", doc_type="policy",
            department="finance", status="active",
        )

    fake_db.get = _get
    resp = client.delete(
        "/api/documents/00000000-0000-0000-0000-0000000000aa", headers=auth_headers
    )
    assert resp.status_code == 403
