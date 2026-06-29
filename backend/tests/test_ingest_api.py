"""API tests for POST /api/ingest and GET /api/ingest/{job_id}/status.

Celery enqueue, Redis, and the DB session are all mocked; the app's lifespan is
never started (TestClient is used without a context manager) so no real Qdrant/
Redis/Postgres connection is opened.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(fake_db, monkeypatch, patch_scope):
    """TestClient with mocked DB session, Celery enqueue, and Redis."""
    from api.main import app
    from core.database import get_session
    import api.routes.ingest as ingest_mod

    app.dependency_overrides[get_session] = lambda: fake_db

    monkeypatch.setattr(
        ingest_mod.ingest_document,
        "delay",
        lambda *args, **kwargs: SimpleNamespace(id="test-job-123"),
    )
    fake_redis = AsyncMock()
    monkeypatch.setattr(ingest_mod, "redis_client", fake_redis)

    test_client = TestClient(app)
    yield test_client, fake_redis
    app.dependency_overrides.clear()


def _pdf_upload(pdf_file):
    return {"file": ("sample.pdf", pdf_file.read_bytes(), "application/pdf")}


def test_ingest_valid_pdf_returns_202(client, pdf_file, auth_headers):
    test_client, _ = client
    resp = test_client.post(
        "/api/ingest",
        files=_pdf_upload(pdf_file),
        data={"doc_type": "policy"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == "test-job-123"
    assert body["document_id"]
    assert body["status"] == "processing"
    assert body["filename"] == "sample.pdf"


def test_ingest_invalid_extension_returns_400(client, auth_headers):
    test_client, _ = client
    resp = test_client.post(
        "/api/ingest",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"doc_type": "policy"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_ingest_missing_doc_type_returns_422(client, pdf_file, auth_headers):
    test_client, _ = client
    resp = test_client.post(
        "/api/ingest",
        files=_pdf_upload(pdf_file),
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_ingest_invalid_doc_type_returns_422(client, pdf_file, auth_headers):
    test_client, _ = client
    resp = test_client.post(
        "/api/ingest",
        files=_pdf_upload(pdf_file),
        data={"doc_type": "banana"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_ingest_file_too_large_returns_413(client, pdf_file, auth_headers, monkeypatch):
    from core.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_FILE_SIZE_MB", 0)
    test_client, _ = client
    resp = test_client.post(
        "/api/ingest",
        files=_pdf_upload(pdf_file),
        data={"doc_type": "policy"},
        headers=auth_headers,
    )
    assert resp.status_code == 413


def test_status_existing_job_returns_200(client, auth_headers):
    test_client, fake_redis = client
    fake_redis.get = AsyncMock(
        return_value=json.dumps(
            {
                "status": "complete",
                "document_id": "doc-1",
                "chunk_count": 7,
            }
        )
    )
    resp = test_client.get("/api/ingest/test-job-123/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "test-job-123"
    assert body["status"] == "complete"
    assert body["chunk_count"] == 7


def test_status_unknown_job_returns_404(client, auth_headers):
    test_client, fake_redis = client
    fake_redis.get = AsyncMock(return_value=None)
    resp = test_client.get("/api/ingest/missing-job/status", headers=auth_headers)
    assert resp.status_code == 404
