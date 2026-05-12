from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


EPIC_RE = re.compile(r"\b([A-Z]{3}\d{6,10})\b")


def _clean(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" \t\r\n:,-")
    # Trim obvious OCR artifacts
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    return value.strip()


def _extract_first(pattern: re.Pattern[str], text: str) -> Optional[str]:
    match = pattern.search(text)
    return match.group(1) if match else None


def parse_elector_records(pages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Heuristic parser for Indian electoral roll OCR output.

    Input shape: list of {"page": int, "text": str}
    Output: {"total_records": int, "records": [ ... ]}
    """
    records: List[Dict[str, Any]] = []

    for page_obj in pages:
        page_num = int(page_obj.get("page") or 0) or None
        text = str(page_obj.get("text") or "")
        if not text.strip():
            continue

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # Collect EPIC-like IDs per line index so we can "attach" them to nearby records.
        epic_by_line: Dict[int, str] = {}
        for i, ln in enumerate(lines):
            epic = _extract_first(EPIC_RE, ln)
            if epic:
                epic_by_line[i] = epic

        i = 0
        while i < len(lines):
            ln = lines[i]

            # Record "start" is usually a Name line (OCR produces many variations).
            name_match = re.search(r"\bName\b\s*[:'!>\-]?\s*(.+)$", ln, flags=re.IGNORECASE)
            if not name_match:
                i += 1
                continue

            name = _clean(name_match.group(1))
            if not name or name.lower().startswith(("and name:", "of polling", "of assembly", "section no")):
                i += 1
                continue

            # Look in a small window around the name for other fields.
            window = lines[i : min(i + 10, len(lines))]
            window_text = "\n".join(window)

            relation_type = None
            relation_name = None
            rel_match = re.search(
                r"\b(Fathers|Father's|Husbands|Husband's|Mothers|Mother's)\s+Name\b\s*[:\-]?\s*(.+)$",
                window_text,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            if rel_match:
                relation_type = rel_match.group(1).lower().replace("'", "")
                relation_name = _clean(rel_match.group(2))

            house_no = None
            house_match = re.search(r"\bHouse\s+Number\b\s*[:=\-]?\s*(.+)$", window_text, flags=re.IGNORECASE | re.MULTILINE)
            if house_match:
                house_no = _clean(house_match.group(1))

            age = None
            age_match = re.search(r"\bAge\b\s*[:=\-]?\s*([0-9]{1,3})\b", window_text, flags=re.IGNORECASE)
            if age_match:
                try:
                    age = int(age_match.group(1))
                except ValueError:
                    age = None

            gender = None
            gender_match = re.search(r"\bGender\b\s*[:=\-]?\s*(Male|Female|Third\s*Gender)\b", window_text, flags=re.IGNORECASE)
            if gender_match:
                gender = _clean(gender_match.group(1)).title()

            # EPIC: nearest within +/- 5 lines from name line.
            epic = None
            for j in range(max(0, i - 5), min(len(lines), i + 6)):
                if j in epic_by_line:
                    epic = epic_by_line[j]
                    break

            # Serial number: often appears at the start of the line preceding the name.
            serial_no = None
            for j in range(max(0, i - 2), i + 1):
                m = re.match(r"^\s*(\d{1,4})\b", lines[j])
                if m:
                    try:
                        serial_no = int(m.group(1))
                        break
                    except ValueError:
                        pass

            records.append(
                {
                    "page": page_num,
                    "serial_no": serial_no,
                    "epic_id": epic,
                    "name": name,
                    "relation_type": relation_type,
                    "relation_name": relation_name,
                    "house_number": house_no,
                    "age": age,
                    "gender": gender,
                }
            )

            i += 1

    return {"total_records": len(records), "records": records}

