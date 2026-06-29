"""Guardrail checks for the SP3 Phase 2 safety layer.

Each module exposes one pure-ish check returning ``{"passed": bool, "detail": str, ...}``.
Expensive/optional checks (hallucination, PII) fail open so a checker failure never
blocks a user answer.
"""
