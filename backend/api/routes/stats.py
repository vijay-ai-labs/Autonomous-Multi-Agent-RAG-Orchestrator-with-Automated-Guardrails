"""Dashboard metrics for the admin stats page.

Aggregates counts and rates across queries, documents, chunks, escalations, and
responses. A refusal is any persisted response whose ``guardrail_result`` is not
``"approved"`` (covers both router/retriever ``"refused"`` and guardrail
``"flagged"`` verdicts).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user
from core.access import UserScope
from core.database import get_session
from models.tables import Document, DocumentChunk, Escalation, Query, Response

router = APIRouter()


@router.get("/stats")
async def get_stats(
    scope: UserScope = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    if not scope.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    total_queries = (
        await db.execute(select(func.count()).select_from(Query))
    ).scalar() or 0
    total_docs = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.status == "active")
        )
    ).scalar() or 0
    total_chunks = (
        await db.execute(select(func.count()).select_from(DocumentChunk))
    ).scalar() or 0
    open_escalations = (
        await db.execute(
            select(func.count())
            .select_from(Escalation)
            .where(Escalation.status == "open")
        )
    ).scalar() or 0

    refused_count = (
        await db.execute(
            select(func.count())
            .select_from(Response)
            .where(Response.guardrail_result.isnot(None))
            .where(Response.guardrail_result != "approved")
        )
    ).scalar() or 0
    refusal_rate = round(refused_count / total_queries * 100, 1) if total_queries else 0.0

    avg_latency = (
        await db.execute(
            select(func.avg(Response.latency_ms)).where(Response.latency_ms.isnot(None))
        )
    ).scalar() or 0

    return {
        "total_queries": total_queries,
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "open_escalations": open_escalations,
        "refusal_rate_pct": refusal_rate,
        "avg_latency_ms": round(avg_latency),
    }
