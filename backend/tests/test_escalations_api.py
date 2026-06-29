"""API tests for the escalation queue endpoints (GET + PATCH).

Auth uses the real JWT dependency (via the ``auth_headers`` fixture). The DB is a
configurable fake whose ``execute`` returns a result exposing ``scalars().all()`` and
``scalar_one_or_none()`` so the routes' query patterns work without Postgres.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _row(**overrides):
    base = dict(
        id=uuid4(),
        query_id=uuid4(),
        reason_code="low_confidence",
        status="open",
        assigned_to=None,
        created_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
        resolved_at=None,
        resolution_notes=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    async def execute(self, *args, **kwargs):
        return _Result(self.rows)

    async def commit(self):
        self.committed = True


def _client(rows):
    from api.main import app
    from core.database import get_session

    session = _FakeSession(rows)
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app), session


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    from api.main import app

    app.dependency_overrides.clear()


def test_list_escalations_returns_200(auth_headers):
    client, _ = _client([_row(), _row(reason_code="toxicity")])
    resp = client.get("/api/escalations", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {"id", "status", "reason_code", "query_id"} <= set(body[0])


def test_list_escalations_status_filter(auth_headers):
    client, _ = _client([_row(status="open")])
    resp = client.get("/api/escalations?status=open", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["status"] == "open"


def test_patch_resolve_returns_200(auth_headers):
    row = _row()
    client, session = _client([row])
    resp = client.patch(
        f"/api/escalations/{row.id}",
        json={"status": "resolved", "resolution_notes": "Fixed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"
    assert row.status == "resolved"
    assert row.resolved_at is not None
    assert session.committed is True


def test_patch_invalid_status_returns_422(auth_headers):
    row = _row()
    client, _ = _client([row])
    resp = client.patch(
        f"/api/escalations/{row.id}", json={"status": "invalid"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_patch_unknown_id_returns_404(auth_headers):
    client, _ = _client([])  # scalar_one_or_none → None
    resp = client.patch(
        f"/api/escalations/{uuid4()}", json={"status": "resolved"}, headers=auth_headers
    )
    assert resp.status_code == 404


def test_list_requires_auth():
    client, _ = _client([_row()])
    resp = client.get("/api/escalations")
    assert resp.status_code in (401, 403)
