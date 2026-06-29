"""Keyword-based toxicity check — no external API, no ML model weights."""

import re

_TOXIC_PATTERNS = [
    r"\b(kill|murder|harm|attack|assault|rape|abuse)\s+(yourself|himself|herself|themselves|people|employees)\b",
    r"\b(hate|despise)\s+(you|all|everyone|them)\b",
    r"\bgo\s+to\s+hell\b",
    r"\b(f+u+c+k+|sh+i+t+|b+i+t+c+h+|a+s+s+h+o+l+e+)\b",
]

_COMPILED = [re.compile(p, re.I) for p in _TOXIC_PATTERNS]


def check_toxicity(text: str) -> dict:
    """
    Returns: {"passed": bool, "detail": str}
    Pass = no toxic content. Keyword-based — no model weights.
    """
    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            return {
                "passed": False,
                "detail": f"Toxic content pattern detected: '{match.group()}'",
            }
    return {"passed": True, "detail": "No toxic content detected."}
