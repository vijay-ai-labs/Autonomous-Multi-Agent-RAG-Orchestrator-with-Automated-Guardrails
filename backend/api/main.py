"""FastAPI application entrypoint.

Wires up the lifespan (DB engine, Qdrant collection, Redis), CORS, request
logging, a global exception handler, and the health router.
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import documents, health, ingest
from api.routes import auth as auth_route
from api.routes import escalations as escalations_route
from api.routes import query as query_route
from api.routes import stats as stats_route
from core.config import get_settings
from core.database import engine
from core.qdrant import close_qdrant, ensure_collection
from core.redis_client import check_redis, close_redis

settings = get_settings()

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("rag.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and tear down backing services."""
    logger.info("Starting up: initializing services")
    # Enable LangSmith tracing for the agent graph when configured.
    if settings.LANGCHAIN_TRACING_V2:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
        logger.info("LangSmith tracing enabled for project: %s", settings.LANGCHAIN_PROJECT)
    # Verify DB connectivity early.
    async with engine.begin():
        logger.info("Database engine connected")
    await ensure_collection()
    await check_redis()
    logger.info("Redis connected")
    logger.info("Application startup complete")
    try:
        yield
    finally:
        logger.info("Shutting down: closing connections")
        await engine.dispose()
        await close_qdrant()
        await close_redis()


app = FastAPI(title="RAG Orchestrator API", version=health.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log method, path, status, and latency for every request."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a 500 with the error message for any unhandled exception."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": str(exc)})


app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(query_route.router, prefix="/api", tags=["query"])
app.include_router(escalations_route.router, prefix="/api", tags=["escalations"])
app.include_router(auth_route.router, prefix="/api", tags=["auth"])
app.include_router(stats_route.router, prefix="/api", tags=["stats"])
