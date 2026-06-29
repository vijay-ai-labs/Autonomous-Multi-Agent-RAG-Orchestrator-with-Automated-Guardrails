"""Tests for Redis-backed session memory with the redis client mocked."""

import json
from unittest.mock import AsyncMock

import pytest

import answer.session as session_mod
from answer.session import (
    MAX_TURNS,
    SESSION_TTL_SECONDS,
    load_session,
    save_session,
)


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the module-level redis client with an AsyncMock."""
    mock = AsyncMock()
    monkeypatch.setattr(session_mod, "redis_client", mock)
    return mock


@pytest.mark.asyncio
async def test_load_session_none_returns_new_uuid_and_empty(fake_redis):
    session_id, messages = await load_session(None)
    assert isinstance(session_id, str) and len(session_id) == 36
    assert messages == []
    fake_redis.get.assert_not_called()


@pytest.mark.asyncio
async def test_load_session_existing_returns_history(fake_redis):
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    fake_redis.get = AsyncMock(return_value=json.dumps(history))
    session_id, messages = await load_session("existing-id")
    assert session_id == "existing-id"
    assert messages == history
    fake_redis.get.assert_awaited_once_with("session:existing-id")


@pytest.mark.asyncio
async def test_load_session_missing_key_returns_empty(fake_redis):
    fake_redis.get = AsyncMock(return_value=None)
    session_id, messages = await load_session("missing-id")
    assert session_id == "missing-id"
    assert messages == []


@pytest.mark.asyncio
async def test_load_session_trims_to_max_turns(fake_redis):
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    fake_redis.get = AsyncMock(return_value=json.dumps(history))
    _, messages = await load_session("id")
    assert len(messages) == MAX_TURNS
    assert messages == history[-MAX_TURNS:]


@pytest.mark.asyncio
async def test_save_session_uses_correct_key_and_ttl(fake_redis):
    messages = [{"role": "user", "content": "x"}]
    await save_session("sid", messages)
    fake_redis.set.assert_awaited_once()
    args, kwargs = fake_redis.set.call_args
    assert args[0] == "session:sid"
    assert json.loads(args[1]) == messages
    assert kwargs["ex"] == SESSION_TTL_SECONDS


@pytest.mark.asyncio
async def test_save_session_trims_to_max_turns(fake_redis):
    messages = [{"role": "user", "content": str(i)} for i in range(10)]
    await save_session("sid", messages)
    args, _ = fake_redis.set.call_args
    stored = json.loads(args[1])
    assert len(stored) == MAX_TURNS
    assert stored == messages[-MAX_TURNS:]
