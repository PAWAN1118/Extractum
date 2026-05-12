from __future__ import annotations

import re
from typing import Any, Dict, Iterable


def extract_elector_summary(pages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    text = "\n".join(str(page.get("text") or "") for page in pages)
    normalized = re.sub(r"\s+", " ", text)

    summary: Dict[str, Any] = {}
    total = _find_total_voters(normalized)
    if total is not None:
        summary["total_voters"] = total

    return summary


def _find_total_voters(text: str) -> int | None:
    patterns = [
        r"\btotal\s+(?:no\.?\s+of\s+)?(?:electors|voters)\b[^0-9]{0,40}([0-9][0-9,]{2,})",
        r"\b(?:electors|voters)\s+total\b[^0-9]{0,40}([0-9][0-9,]{2,})",
        r"\btotal\b[^0-9]{0,30}\bmale\b[^0-9]{0,20}[0-9,]+\b[^0-9]{0,30}\bfemale\b[^0-9]{0,20}[0-9,]+\b[^0-9]{0,30}([0-9][0-9,]{2,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _to_int(match.group(1))
    return None


def _to_int(value: str) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
