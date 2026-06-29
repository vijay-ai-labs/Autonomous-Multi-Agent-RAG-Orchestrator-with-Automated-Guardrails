"""API tests for POST /api/query with the pipeline mocked.

The real pipeline is never invoked; ``run_query_pipeline`` is patched to return
a fixed QueryResponse. Auth and the DB session are overridden/mocked so no real
Redis/Postgres/Qdrant connection is opened.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from answer.schemas import Citation, QueryResponse


def _answer_response() -> QueryResponse:
    return QueryResponse(
        query_id="q-123",
        session_id="sess-1",
        answer="Employees get 20 days [Source 1].",
        citations=[
            Citation(
                source_num=1,
                filename="handbook.pdf",
                page_number=3,
                section="Vacation",
                excerpt="Employees get 20 days.",
                document_id="doc-1",
            )
        ],
        confidence=0.82,
        refused=False,
    )


def _refusal_response() -> QueryResponse:
    return QueryResponse(
        query_id="q-456",
        session_id="sess-1",
        answer="I don't have reliable information...",
        citations=[],
        confidence=0.0,
        refused=True,
        refusal_reason="No relevant documents found",
    )


@pytest.fixture
def client(fake_db, monkeypatch, patch_scope):
    """TestClient with mocked pipeline and DB session."""
    from api.main import app
    from core.database import get_session
    import api.routes.query as query_mod

    app.dependency_overrides[get_session] = lambda: fake_db

    pipeline_mock = AsyncMock(return_value=_answer_response())
    monkeypatch.setattr(query_mod, "run_query_pipeline", pipeline_mock)

    test_client = TestClient(app)
    yield test_client, pipeline_mock
    app.dependency_overrides.clear()


def test_valid_query_returns_200(client, auth_headers):
    test_client, _ = client
    resp = test_client.post(
        "/api/query", json={"query": "vacation policy?"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"]
    assert body["session_id"] == "sess-1"
    assert body["refused"] is False
    assert len(body["citations"]) == 1
    assert body["citations"][0]["source_num"] == 1


def test_empty_query_returns_422(client, auth_headers):
    test_client, _ = client
    resp = test_client.post("/api/query", json={"query": ""}, headers=auth_headers)
    assert resp.status_code == 422


def test_overlong_query_returns_422(client, auth_headers):
    test_client, _ = client
    resp = test_client.post(
        "/api/query", json={"query": "x" * 2001}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_missing_auth_returns_401(client):
    test_client, _ = client
    resp = test_client.post("/api/query", json={"query": "hi"})
    assert resp.status_code in (401, 403)


def test_refused_query_returns_200_with_refusal(client, auth_headers, monkeypatch):
    test_client, pipeline_mock = client
    pipeline_mock.return_value = _refusal_response()
    resp = test_client.post(
        "/api/query", json={"query": "weather in Paris?"}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is True
    assert body["refusal_reason"] == "No relevant documents found"
    assert body["citations"] == []


def test_session_continuity_returns_same_session_id(client, auth_headers):
    test_client, pipeline_mock = client
    resp = test_client.post(
        "/api/query",
        json={"query": "follow up?", "session_id": "sess-1"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-1"
    # pipeline received the inbound session_id
    assert pipeline_mock.call_args.kwargs["session_id"] == "sess-1"
