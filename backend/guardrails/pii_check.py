"""PII detection via presidio-analyzer. Fail-open: presidio is optional."""

import logging

logger = logging.getLogger(__name__)

_PII_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
    "US_SSN", "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS",
]


def check_pii(text: str) -> dict:
    """
    Scan text for PII entities using presidio-analyzer.
    Returns: {"passed": bool, "detail": str, "entities_found": list[str]}
    Fail-open: if presidio not installed, returns passed=True with warning.
    """
    try:
        from presidio_analyzer import AnalyzerEngine
        analyzer = AnalyzerEngine()
        results = analyzer.analyze(text=text, entities=_PII_ENTITIES, language="en")
        if results:
            entity_types = list({r.entity_type for r in results})
            return {
                "passed": False,
                "detail": f"PII detected: {entity_types}",
                "entities_found": entity_types,
            }
        return {"passed": True, "detail": "No PII detected.", "entities_found": []}
    except ImportError:
        logger.warning("presidio-analyzer not installed; PII check skipped")
        return {"passed": True, "detail": "PII check skipped (presidio not installed)", "entities_found": []}
    except Exception as exc:
        logger.warning("PII check error: %s", exc)
        return {"passed": True, "detail": f"PII check skipped: {exc}", "entities_found": []}
