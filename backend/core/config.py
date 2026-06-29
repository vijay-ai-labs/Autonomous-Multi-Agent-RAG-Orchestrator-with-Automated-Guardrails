"""Application configuration loaded from environment / .env file.

All settings are read once and cached via :func:`get_settings`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    POSTGRES_URL: str  # postgresql+asyncpg://user:password@host:5432/rag_db

    # Qdrant
    QDRANT_URL: str  # http://localhost:6333
    QDRANT_COLLECTION: str = "company_docs"

    # Redis
    REDIS_URL: str  # redis://localhost:6379/0

    # OpenAI (not used in Phase 1, defined for Phase 2+)
    OPENAI_API_KEY: str
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_LLM_MODEL: str = "gpt-4o"
    OPENAI_GUARDRAIL_MODEL: str = "gpt-4o-mini"

    # Auth
    JWT_SECRET: str
    JWT_EXPIRY_HOURS: int = 8

    # LangSmith
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "rag-orchestrator"
    LANGCHAIN_TRACING_V2: bool = False

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ESCALATION_EMAIL: str = ""

    # App
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    MAX_FILE_SIZE_MB: int = 50
    MAX_CHUNKS_PER_QUERY: int = 8
    EVIDENCE_THRESHOLD: float = 0.6
    FAITHFULNESS_THRESHOLD: float = 0.7

    # CORS — comma-separated origins; "*" allows all (dev default)
    CORS_ORIGINS: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse ``CORS_ORIGINS`` into a list for the CORS middleware."""
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
