from __future__ import annotations

import re
from typing import Dict, Any, List, Tuple


# (label, severity_weight, regex)
AMBIGUITY_PATTERNS: List[Tuple[str, int, re.Pattern]] = [
    ("reasonable", 2, re.compile(r"\breasonable\b", re.I)),
    ("best efforts", 3, re.compile(r"\bbest efforts\b|\bcommercially reasonable efforts\b", re.I)),
    ("promptly / asap", 2, re.compile(r"\b(promptly|as soon as possible|asap)\b", re.I)),
    ("material / substantial", 3, re.compile(r"\b(material|substantial)\b", re.I)),
    ("from time to time", 2, re.compile(r"\bfrom time to time\b", re.I)),
    ("including but not limited to", 2, re.compile(r"\bincluding\b.*\bnot limited to\b", re.I)),
    ("sole discretion", 4, re.compile(r"\bsole discretion\b|\bat (its|their) discretion\b", re.I)),
    ("to the satisfaction of", 3, re.compile(r"\bto the satisfaction of\b|\bsatisfactory to\b", re.I)),
    ("as determined by", 3, re.compile(r"\bas determined by\b|\bas decided by\b", re.I)),
    ("may amend / may change", 3, re.compile(r"\bmay (amend|modify|change)\b", re.I)),
    ("in its opinion", 3, re.compile(r"\bin (its|their) opinion\b", re.I)),
    ("as applicable", 2, re.compile(r"\bas applicable\b", re.I)),
    ("etc / and so on", 1, re.compile(r"\betc\.\b|\band so on\b", re.I)),
]

SENT_SPLIT = re.compile(r"(?<=[\.\n;:])\s+")


def _snippet(sentence: str, match_span: Tuple[int, int], window: int = 70) -> str:
    s, e = match_span
    start = max(0, s - window)
    end = min(len(sentence), e + window)
    return sentence[start:end].strip()


def detect_ambiguity(text: str, max_hits: int = 20) -> Dict[str, Any]:
    """
    Rule-based ambiguity detection.

    Returns:
      {
        "hits": [
          {"label": "...", "weight": 3, "match": "reasonable", "snippet": "..."}
        ],
        "score": int,
        "level": "Low|Medium|High",
        "recommendations": [...]
      }
    """
    t = text or ""
    sentences = SENT_SPLIT.split(t)

    hits: List[Dict[str, Any]] = []
    score = 0

    for sent in sentences:
        if not sent or len(sent) < 8:
            continue

        for label, weight, pat in AMBIGUITY_PATTERNS:
            m = pat.search(sent)
            if not m:
                continue

            hits.append(
                {
                    "label": label,
                    "weight": weight,
                    "match": m.group(0),
                    "snippet": _snippet(sent, (m.start(), m.end())),
                }
            )
            score += weight

            if len(hits) >= max_hits:
                break

        if len(hits) >= max_hits:
            break

    if score >= 10:
        level = "High"
    elif score >= 5:
        level = "Medium"
    elif score >= 1:
        level = "Low"
    else:
        level = "None"

    recommendations = [
        "Replace vague terms with measurable definitions (numbers, deadlines, thresholds).",
        "Define who decides and how decisions are communicated (avoid 'sole discretion' without constraints).",
        "For timelines, specify exact days (e.g., 'within 7 days') instead of 'promptly/asap'.",
        "For 'reasonable/best efforts', define minimum actions and acceptable evidence of efforts.",
        "For 'material/substantial', define objective criteria or examples.",
    ]

    return {
        "hits": hits,
        "score": score,
        "level": level,
        "recommendations": recommendations,
    }


def format_ambiguity_as_text(amb: Dict[str, Any]) -> str:
    if not amb:
        return "No ambiguity analysis available."

    level = amb.get("level", "None")
    score = amb.get("score", 0)
    hits = amb.get("hits", []) or []
    recs = amb.get("recommendations", []) or []

    lines = [f"Ambiguity Level: {level} | Score: {score}", ""]

    if not hits:
        lines.append("No ambiguous phrases detected.")
    else:
        lines.append("Ambiguous Phrases (examples):")
        for h in hits[:15]:
            lines.append(f"- [{h.get('label')}] match='{h.get('match')}'")
            lines.append(f"  snippet: {h.get('snippet')}")
        if len(hits) > 15:
            lines.append(f"... ({len(hits) - 15} more hits)")
    lines.append("")
    lines.append("Recommendations to clarify:")
    for r in recs[:6]:
        lines.append(f"- {r}")

    return "\n".join(lines).strip()

