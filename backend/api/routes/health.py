"""Health endpoint reporting the status of all backing services."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.qdrant import check_qdrant
from core.redis_client import check_redis

logger = logging.getLogger(__name__)

router = APIRouter()

VERSION = "1.0.0"


async def _check_database(session: AsyncSession) -> bool:
    await session.execute(text("SELECT 1"))
    return True


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Return aggregate health of database, Qdrant, and Redis.

    200 + ``healthy`` when all checks pass; 503 + ``degraded`` otherwise, with
    each failing service marked in ``checks``.
    """
    checks: dict[str, str] = {}

    for name, coro in (
        ("database", _check_database(session)),
        ("qdrant", check_qdrant()),
        ("redis", check_redis()),
    ):
        try:
            await coro
            checks[name] = "ok"
        except Exception as exc:  # noqa: BLE001 — report any failure as degraded
            logger.warning("Health check failed for %s: %s", name, exc)
            checks[name] = "error"

    all_ok = all(value == "ok" for value in checks.values())
    body = {
        "status": "healthy" if all_ok else "degraded",
        "version": VERSION,
        "checks": checks,
    }
    return JSONResponse(status_code=200 if all_ok else 503, content=body)
