"""Async Redis connection and a lightweight health check."""

import logging

import redis.asyncio as aioredis

from core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

client: aioredis.Redis = aioredis.from_url(
    _settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


async def check_redis() -> bool:
    """Return ``True`` if Redis responds to PING."""
    return await client.ping()


async def close_redis() -> None:
    """Close the Redis connection pool."""
    await client.aclose()
