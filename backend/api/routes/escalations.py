"""Escalation queue API: list pending escalations and update their status.

Both endpoints require a valid JWT (``get_current_user_id``) and use the request-scoped
DB session. The escalation rows themselves are created by the agent graph's persist node.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user_id
from core.database import get_session
from models.tables import Escalation

router = APIRouter()


class EscalationUpdate(BaseModel):
    status: str                    # "in_progress" | "resolved"
    assigned_to: str | None = None
    resolution_notes: str | None = None


@router.get("/escalations")
async def list_escalations(
    status: str | None = None,     # filter by status
    limit: int = 50,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """List escalations. Optionally filter by status."""
    stmt = select(Escalation).order_by(Escalation.created_at.desc()).limit(min(limit, 200))
    if status:
        stmt = stmt.where(Escalation.status == status)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "query_id": str(r.query_id),
            "reason_code": r.reason_code,
            "status": r.status,
            "assigned_to": r.assigned_to,
            "created_at": r.created_at.isoformat(),
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "resolution_notes": r.resolution_notes,
        }
        for r in rows
    ]


@router.patch("/escalations/{escalation_id}")
async def update_escalation(
    escalation_id: UUID,
    update: EscalationUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Update escalation status (assign or resolve)."""
    allowed = {"in_progress", "resolved"}
    if update.status not in allowed:
        raise HTTPException(status_code=422, detail=f"status must be one of {allowed}")

    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Escalation not found")

    row.status = update.status
    if update.assigned_to:
        row.assigned_to = update.assigned_to
    if update.resolution_notes:
        row.resolution_notes = update.resolution_notes
    if update.status == "resolved":
        from datetime import datetime, timezone

        row.resolved_at = datetime.now(timezone.utc)

    await db.commit()
    return {"id": str(row.id), "status": row.status, "message": "Updated"}
