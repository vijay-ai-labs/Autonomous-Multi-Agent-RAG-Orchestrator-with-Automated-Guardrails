"""Redis-backed conversation session memory.

Stores the last ``MAX_TURNS`` messages per session under ``session:{id}`` as a
JSON list, with a 1-hour TTL refreshed on every save.
"""

import json
import uuid

from core.redis_client import client as redis_client

SESSION_TTL_SECONDS = 3600
MAX_TURNS = 6  # last 6 messages (3 user + 3 assistant exchanges)


async def load_session(session_id: str | None) -> tuple[str, list[dict]]:
    """Load conversation history for ``session_id``.

    If ``session_id`` is None or the key is missing: return ``(new_uuid, [])``.
    Always returns ``(session_id, messages)`` where messages are
    ``[{"role": "user"|"assistant", "content": str}, ...]`` trimmed to MAX_TURNS.
    """
    if session_id is None:
        return str(uuid.uuid4()), []
    raw = await redis_client.get(f"session:{session_id}")
    if raw is None:
        return session_id, []
    messages = json.loads(raw)
    return session_id, messages[-MAX_TURNS:]  # trim to last MAX_TURNS


async def save_session(session_id: str, messages: list[dict]) -> None:
    """Trim to MAX_TURNS and save back to Redis, resetting the TTL."""
    trimmed = messages[-MAX_TURNS:]
    await redis_client.set(
        f"session:{session_id}",
        json.dumps(trimmed),
        ex=SESSION_TTL_SECONDS,
    )
