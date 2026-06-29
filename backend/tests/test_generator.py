"""Tests for GPT-4o answer generation with the OpenAI client mocked."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import answer.generator as gen
from answer.generator import SYSTEM_PROMPT, generate_answer
from core.config import get_settings


@pytest.fixture
def patched_openai(monkeypatch):
    """Patch openai.AsyncOpenAI; return the create mock for assertions."""
    create_mock = AsyncMock(
        return_value=MagicMock(
            choices=[MagicMock(message=MagicMock(content="  Answer [Source 1].  "))]
        )
    )
    fake_client = MagicMock()
    fake_client.chat.completions.create = create_mock
    monkeypatch.setattr(gen.openai, "AsyncOpenAI", lambda **kwargs: fake_client)
    return create_mock


@pytest.mark.asyncio
async def test_uses_configured_model(patched_openai):
    await generate_answer("vacation days?", "<context>", [])
    _, kwargs = patched_openai.call_args
    assert kwargs["model"] == get_settings().OPENAI_LLM_MODEL


@pytest.mark.asyncio
async def test_system_prompt_is_first_message(patched_openai):
    await generate_answer("vacation days?", "<context>", [])
    messages = patched_openai.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_context_injected_before_query(patched_openai):
    await generate_answer("vacation days?", "MY_CONTEXT_BLOCK", [])
    messages = patched_openai.call_args.kwargs["messages"]
    context_idx = next(
        i for i, m in enumerate(messages) if "MY_CONTEXT_BLOCK" in m["content"]
    )
    query_idx = next(
        i for i, m in enumerate(messages) if m["content"] == "vacation days?"
    )
    assert context_idx < query_idx


@pytest.mark.asyncio
async def test_temperature_is_low(patched_openai):
    await generate_answer("q", "<context>", [])
    assert patched_openai.call_args.kwargs["temperature"] == 0.1


@pytest.mark.asyncio
async def test_history_ordered_between_context_and_query(patched_openai):
    history = [
        {"role": "user", "content": "prev q"},
        {"role": "assistant", "content": "prev a"},
    ]
    await generate_answer("current q", "MY_CONTEXT_BLOCK", history)
    messages = patched_openai.call_args.kwargs["messages"]
    context_idx = next(
        i for i, m in enumerate(messages) if "MY_CONTEXT_BLOCK" in m["content"]
    )
    prev_q_idx = next(i for i, m in enumerate(messages) if m["content"] == "prev q")
    prev_a_idx = next(i for i, m in enumerate(messages) if m["content"] == "prev a")
    query_idx = next(i for i, m in enumerate(messages) if m["content"] == "current q")
    assert context_idx < prev_q_idx < prev_a_idx < query_idx


@pytest.mark.asyncio
async def test_returns_stripped_content(patched_openai):
    result = await generate_answer("q", "<context>", [])
    assert result == "Answer [Source 1]."
