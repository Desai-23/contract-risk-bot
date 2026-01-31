from __future__ import annotations

import re
from typing import Dict, Any, List

# Prohibition first (most specific)
PROHIBITION_PAT = re.compile(
    r"\b(shall not|must not|may not|is prohibited from|are prohibited from|will not)\b",
    re.I,
)

# Obligation patterns
OBLIGATION_PAT = re.compile(
    r"\b(shall|must|is required to|are required to|undertakes to|agrees to)\b",
    re.I,
)

# Rights / permissions patterns
RIGHT_PAT = re.compile(
    r"\b(may|can|is entitled to|are entitled to|has the right to|have the right to)\b",
    re.I,
)

# Split into candidates (simple + robust)
SENT_SPLIT = re.compile(r"(?<=[\.\n;:])\s+")


def _clean(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def extract_deontic_statements(text: str, max_each: int = 12) -> Dict[str, Any]:
    """
    Extract obligations / rights / prohibitions from normalized English text.
    Rule-based: keyword/modal detection.

    Returns JSON-safe dict with lists + counts.
    """
    t = text or ""
    candidates = SENT_SPLIT.split(t)

    obligations: List[str] = []
    rights: List[str] = []
    prohibitions: List[str] = []

    for cand in candidates:
        s = _clean(cand)
        if not s or len(s) < 15:
            continue

        # categorize with precedence
        if PROHIBITION_PAT.search(s):
            prohibitions.append(s)
        elif OBLIGATION_PAT.search(s):
            obligations.append(s)
        elif RIGHT_PAT.search(s):
            rights.append(s)

        if len(obligations) >= max_each and len(rights) >= max_each and len(prohibitions) >= max_each:
            break

    obligations = _dedupe(obligations)[:max_each]
    rights = _dedupe(rights)[:max_each]
    prohibitions = _dedupe(prohibitions)[:max_each]

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




