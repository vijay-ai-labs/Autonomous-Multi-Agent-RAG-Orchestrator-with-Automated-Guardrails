"""Unit tests for the individual guardrail check functions.

Citation/toxicity are pure. PII is fail-open (skips gracefully when presidio/spaCy
absent). Hallucination mocks the OpenAI client so no network call is made.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from guardrails.citation_check import check_citations
from guardrails.hallucination_check import check_hallucination
from guardrails.pii_check import check_pii
from guardrails.toxicity_check import check_toxicity

# --------------------------------------------------------------------------
# Citation checks
# --------------------------------------------------------------------------

_CITATIONS = [{"source_num": 1, "filename": "handbook.pdf"}]


def test_citation_pass_when_marker_present():
    result = check_citations("Employees get 20 days [Source 1].", _CITATIONS)
    assert result["passed"] is True
    assert result["citation_count"] == 1


def test_citation_fail_when_no_marker():
    result = check_citations("Employees get 20 days.", _CITATIONS)
    assert result["passed"] is False
    assert result["citation_count"] == 0


def test_citation_fail_when_no_citations_available():
    result = check_citations("Anything [Source 1].", [])
    assert result["passed"] is False
    assert "No citations available" in result["detail"]


def test_citation_counts_unique_markers():
    answer = "A [Source 1]. B [Source 2]. C [Source 1] again."
    result = check_citations(answer, _CITATIONS)
    assert result["passed"] is True
    assert result["citation_count"] == 2
    assert "2 unique" in result["detail"]


# --------------------------------------------------------------------------
# Toxicity checks
# --------------------------------------------------------------------------


def test_toxicity_pass_on_clean_text():
    assert check_toxicity("The vacation policy allows 15 days.")["passed"] is True


def test_toxicity_fail_on_profanity():
    # Pattern matches repeated letters of the literal word, not asterisk-masked forms.
    result = check_toxicity("fuck this policy")
    assert result["passed"] is False


def test_toxicity_fail_on_go_to_hell():
    assert check_toxicity("go to hell")["passed"] is False


# --------------------------------------------------------------------------
# PII checks (fail-open when presidio/spaCy model not installed)
# --------------------------------------------------------------------------


def test_pii_clean_text_passes():
    result = check_pii("The policy states 15 vacation days.")
    # Either presidio found nothing, or it is not installed → both pass.
    assert result["passed"] is True


def test_pii_skips_gracefully_without_presidio(monkeypatch):
    """Force the ImportError path and assert fail-open."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("presidio_analyzer"):
            raise ImportError("presidio not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = check_pii("Contact John Smith at john@company.com")
    assert result["passed"] is True
    assert result["entities_found"] == []
    assert "skipped" in result["detail"].lower()


# --------------------------------------------------------------------------
# Hallucination check (OpenAI mocked)
# --------------------------------------------------------------------------


def _mock_openai(monkeypatch, *, content: str | None = None, raise_exc: Exception | None = None):
    """Patch openai.AsyncOpenAI to return a client whose create() is controlled."""
    if raise_exc is not None:
        create = AsyncMock(side_effect=raise_exc)
    else:
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        response = SimpleNamespace(choices=[choice])
        create = AsyncMock(return_value=response)

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    import guardrails.hallucination_check as mod

    monkeypatch.setattr(mod.openai, "AsyncOpenAI", lambda *a, **kw: fake_client)


@pytest.mark.asyncio
async def test_hallucination_pass(monkeypatch):
    _mock_openai(monkeypatch, content="PASS: All claims supported")
    result = await check_hallucination("Answer [Source 1].", "context")
    assert result["passed"] is True


@pytest.mark.asyncio
async def test_hallucination_fail(monkeypatch):
    _mock_openai(monkeypatch, content="FAIL: The answer claims 30 days which is not in context")
    result = await check_hallucination("Answer [Source 1].", "context")
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_hallucination_fail_open_on_error(monkeypatch):
    _mock_openai(monkeypatch, raise_exc=RuntimeError("openai down"))
    result = await check_hallucination("Answer [Source 1].", "context")
    assert result["passed"] is True
    assert "skipped" in result["detail"]
