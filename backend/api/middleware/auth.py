"""JWT Bearer authentication.

Phase 1 provides token decoding/validation only — no login or register
endpoints. ``sub`` carries the user id (UUID string). Tokens are signed with
HS256 using ``JWT_SECRET`` and expire after ``JWT_EXPIRY_HOURS``.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from core.access import UserScope
from core.config import get_settings
from core.database import async_session_factory
from core.redis_client import client as redis_client
from models.tables import User

ALGORITHM = "HS256"

_bearer = HTTPBearer(auto_error=True)

# How long a resolved UserScope is cached in Redis. Short so role/department
# changes (and revocations) take effect quickly without a DB hit per request.
SCOPE_CACHE_TTL_SECONDS = 60


def _scope_key(user_id: UUID) -> str:
    return f"userscope:{user_id}"


def create_access_token(user_id: UUID, expires_hours: int | None = None) -> str:
    """Create a signed JWT for ``user_id``. Intended for tests/tooling."""
    settings = get_settings()
    hours = expires_hours if expires_hours is not None else settings.JWT_EXPIRY_HOURS
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=hours),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def _decode(token: str) -> UUID:
    """Decode and validate a JWT, returning the ``sub`` user id as a UUID."""
    settings = get_settings()
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise credentials_error from exc

    subject = payload.get("sub")
    if subject is None:
        raise credentials_error
    try:
        return UUID(subject)
    except (ValueError, TypeError) as exc:
        raise credentials_error from exc


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> UUID:
    """FastAPI dependency returning the authenticated user's id.

    Raises 401 if the bearer token is missing, malformed, or expired.
    """
    return _decode(credentials.credentials)


async def _load_scope(user_id: UUID) -> UserScope:
    """Resolve a user's RBAC scope, reading through a short-lived Redis cache.

    On a cache miss the user row is loaded from Postgres and the result is
    cached under ``userscope:{id}`` for ``SCOPE_CACHE_TTL_SECONDS``.
    """
    cached = await redis_client.get(_scope_key(user_id))
    if cached is not None:
        data = json.loads(cached)
        return UserScope(
            id=user_id, role=data["role"], departments=tuple(data["departments"])
        )

    async with async_session_factory() as session:
        user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists",
        )

    departments = list(user.departments or [])
    await redis_client.set(
        _scope_key(user_id),
        json.dumps({"role": user.role, "departments": departments}),
        ex=SCOPE_CACHE_TTL_SECONDS,
    )
    return UserScope(id=user_id, role=user.role, departments=tuple(departments))


async def get_current_user(
    user_id: UUID = Depends(get_current_user_id),
) -> UserScope:
    """FastAPI dependency returning the authenticated user's RBAC scope.

    Layered on :func:`get_current_user_id` so token validation (and its 401)
    runs first, then the scope is resolved from DB/Redis.
    """
    return await _load_scope(user_id)


async def invalidate_user_scope(user_id: UUID) -> None:
    """Drop a user's cached scope so the next request reloads it from Postgres.

    Call after changing a user's role or department membership.
    """
    await redis_client.delete(_scope_key(user_id))
