"""SQLAlchemy 2.x ORM models for all relational tables.

Tables: users, documents, document_chunks, queries, responses, escalations,
audit_log. UUID primary keys default to ``gen_random_uuid()`` at the database
level; timestamps default to ``NOW()``.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ARRAY, Float, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'employee'"))
    departments: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'")
    )
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    last_active: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[UUID] = _uuid_pk()
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_date: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'processing'")
    )
    uploader_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[UUID] = _uuid_pk()
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    qdrant_point_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    agent_trace_id: Mapped[str | None] = mapped_column(Text, nullable=True)


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[UUID] = _uuid_pk()
    query_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("queries.id"), nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    guardrail_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrail_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[UUID] = _uuid_pk()
    query_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("queries.id"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'open'"))
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = _uuid_pk()
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
