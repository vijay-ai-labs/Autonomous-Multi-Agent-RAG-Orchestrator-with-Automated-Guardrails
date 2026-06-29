"""POST /api/query — full retrieve → answer/refuse → persist endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from answer.pipeline import run_query_pipeline
from answer.schemas import QueryRequest, QueryResponse
from api.middleware.auth import get_current_user
from core.access import UserScope, department_allowed, deny_access
from core.database import get_session

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    scope: UserScope = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> QueryResponse:
    """Submit a question. Returns a grounded answer with citations or a refusal.

    Any client-supplied ``department`` is only honoured as a narrowing filter
    within the caller's RBAC scope; an out-of-scope value is rejected (403)
    rather than silently widening or emptying the result.
    """
    if not department_allowed(scope, request.department):
        await deny_access(db, scope, request.department, "query")

    return await run_query_pipeline(
        query_text=request.query,
        session_id=request.session_id,
        user_id=scope.id,
        user_role=scope.role,
        user_departments=list(scope.departments),
        doc_type=request.doc_type,
        department=request.department,
        db=db,
    )
