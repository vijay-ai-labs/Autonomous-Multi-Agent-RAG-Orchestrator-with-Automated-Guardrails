"""Env defaults for the eval suites.

The adversarial tests import ``agents.*`` modules, which pull in ``core.config``
``Settings`` at import time. This sets harmless test values before any such
import so the no-default settings fields resolve without a live environment —
mirroring ``backend/tests/conftest.py``. Nothing here opens a real connection.
"""

import os

os.environ.setdefault(
    "POSTGRES_URL", "postgresql+asyncpg://user:pass@localhost:5432/rag_test"
)
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
