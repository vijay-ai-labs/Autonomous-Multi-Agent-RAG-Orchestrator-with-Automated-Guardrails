"""Citation coverage check: the answer must carry at least one ``[Source N]`` marker."""

import re

_CITATION_PATTERN = re.compile(r"\[Source\s+\d+\]", re.I)


def check_citations(answer: str, citations: list[dict]) -> dict:
    """
    Pass when answer contains at least one [Source N] citation.
    If citations list is empty (should not happen after answer node), fail.

    Returns: {"passed": bool, "detail": str, "citation_count": int}
    """
    if not citations:
        return {"passed": False, "detail": "No citations available to validate.", "citation_count": 0}
    found = _CITATION_PATTERN.findall(answer)
    count = len(set(found))   # unique citations
    if count == 0:
        return {
            "passed": False,
            "detail": "Answer contains no [Source N] citations. Expected at least 1.",
            "citation_count": 0,
        }
    return {"passed": True, "detail": f"{count} unique citation(s) found.", "citation_count": count}
