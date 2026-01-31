from __future__ import annotations

import re
from typing import Dict, List, Any


# Basic modal patterns
OBLIGATION_PAT = re.compile(r"\b(shall|must|is required to|are required to|will)\b", re.I)
RIGHT_PAT = re.compile(r"\b(may|is entitled to|are entitled to|can)\b", re.I)
PROHIBITION_PAT = re.compile(r"\b(shall not|must not|may not|is prohibited from|are prohibited from)\b", re.I)


def _clean_line(line: str) -> str:
    line = (line or "").strip()
    line = re.sub(r"\s+", " ", line)
    return line


def extract_deontic_statements(text: str, max_items_each: int = 12) -> Dict[str, Any]:
    """
    Extracts obligation/right/prohibition sentences using rule-based matching.

    Output:
    {
      "obligations": [...],
      "rights": [...],
      "prohibitions": [...],
      "counts": {"obligations": n, "rights": n, "prohibitions": n}
    }
    """
    t = text or ""
    # Split roughly into sentences/lines
    candidates = re.split(r"(?<=[.;:\n])\s+", t)

    obligations: List[str] = []
    rights: List[str] = []
    prohibitions: List[str] = []

    for c in candidates:
        s = _clean_line(c)
        if not s or len(s) < 12:
            continue

        # Prohibition first (more specific)
        if PROHIBITION_PAT.search(s):
            prohibitions.append(s)
        elif OBLIGATION_PAT.search(s):
            obligations.append(s)
        elif RIGHT_PAT.search(s):
            rights.append(s)

        if len(obligations) >= max_items_each and len(rights) >= max_items_each and len(prohibitions) >= max_items_each:
            break

    # Dedupe preserving order
    def dedupe(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in items:
            k = x.lower()
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out

    obligations = dedupe(obligations)[:max_items_each]
    rights = dedupe(rights)[:max_items_each]
    prohibitions = dedupe(prohibitions)[:max_items_each]

    return {
        "obligations": obligations,
        "rights": rights,
        "prohibitions": prohibitions,
        "counts": {
            "obligations": len(obligations),
            "rights": len(rights),
            "prohibitions": len(prohibitions),
        },
    }


def format_deontic_as_text(deontic: Dict[str, Any]) -> str:
    if not deontic:
        return "No obligations/rights/prohibitions extracted."

    def section(title: str, items: List[str]) -> str:
        if not items:
            return f"{title}: None"
        return title + ":\n" + "\n".join([f"- {x}" for x in items])

    return "\n\n".join(
        [
            section("OBLIGATIONS", deontic.get("obligations", [])),
            section("RIGHTS / PERMISSIONS", deontic.get("rights", [])),
            section("PROHIBITIONS", deontic.get("prohibitions", [])),
        ]
    )
