"""RBAC access-control primitives: the user's document scope and the rules
deciding which departments that scope may reach.

Scope is always derived from the authenticated user server-side — never from
client-supplied filters. ``admin`` sees everything; ``manager``/``employee`` see
documents in their ``departments`` plus shared (``department IS NULL``) docs.

This module is intentionally free of FastAPI request plumbing so the rules stay
unit-testable in isolation. ``deny_access`` is the one place that records a
denial to the audit log and raises the HTTP error.
"""

from dataclasses import dataclass
from typing import NoReturn
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.tables import AuditLog


@dataclass(frozen=True)
class UserScope:
    """The authenticated caller's identity and document reach."""

    id: UUID
    role: str  # "admin" | "manager" | "employee"
    departments: tuple[str, ...]  # empty for admin (means "all")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def department_allowed(scope: UserScope, department: str | None) -> bool:
    """Whether ``scope`` may *read* documents in ``department``.

    ``None`` means "no department narrowing requested" / shared docs, which is
    always permitted on the read path. Admins may read any department.
    """
    if scope.is_admin:
        return True
    if department is None:
        return True
    return department in scope.departments


def can_write_department(scope: UserScope, department: str | None) -> bool:
    """Whether ``scope`` may *create/modify* a document in ``department``.

    Stricter than the read rule: only an admin may write shared (``None``)
    documents; everyone else must target a department they belong to.
    """
    if scope.is_admin:
        return True
    if department is None:
        return False
    return department in scope.departments


async def deny_access(
    db: AsyncSession,
    scope: UserScope,
    attempted_department: str | None,
    endpoint: str,
) -> NoReturn:
    """Record an access-denied audit event and raise HTTP 403.

    Always raises — callers do not need a ``return`` after this call.
    """
    db.add(
        AuditLog(
            event_type="access_denied",
            entity_id=scope.id,
            details={
                "user_id": str(scope.id),
                "role": scope.role,
                "attempted_department": attempted_department,
                "endpoint": endpoint,
            },
        )
    )
    await db.commit()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to the requested department",
    )
