from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Any, Tuple

from src.risk.patterns import detect_red_flags, RedFlag


@dataclass
class ClauseAnalysis:
    clause_id: str
    clause_text: str
    clause_type: str
    risk_level: str  # Low | Medium | High | Unclear
    risk_reason: str


def _risk_to_score(risk: str) -> int:
    if risk == "High":
        return 3
    if risk == "Medium":
        return 2
    if risk == "Low":
        return 1
    return 1  # Unclear treated as low-ish but we track it


def _score_to_overall(avg_score: float) -> str:
    if avg_score >= 2.3:
        return "High"
    if avg_score >= 1.7:
        return "Medium"
    return "Low"


def aggregate_contract(clauses: List[ClauseAnalysis]) -> Dict[str, Any]:
    """
    Aggregates clause-level risks into a contract-level score.
    Also runs rule-based red flag detection across the whole contract text.
    """

    if not clauses:
        return {
            "overall_risk": "Unclear",
            "avg_score": 0.0,
            "counts": {"High": 0, "Medium": 0, "Low": 0, "Unclear": 0},
            "top_high_risk": [],
            "red_flags": [],
        }

    counts = {"High": 0, "Medium": 0, "Low": 0, "Unclear": 0}
    total = 0

    for c in clauses:
        counts[c.risk_level] = counts.get(c.risk_level, 0) + 1
        total += _risk_to_score(c.risk_level)

    avg = total / max(len(clauses), 1)
    overall = _score_to_overall(avg)

    # Top high-risk clauses for summary
    high_risk = [c for c in clauses if c.risk_level == "High"]
    high_risk_sorted = high_risk[:8]  # cap for UI

    # Rule-based red flags across all text
    full_text = "\n".join([c.clause_text for c in clauses])
    flags = detect_red_flags(full_text)

    # Convert flags to dicts for UI
    flags_out = [{"flag_type": f.flag_type, "severity": f.severity, "reason": f.reason} for f in flags]

    return {
        "overall_risk": overall,
        "avg_score": round(avg, 2),
        "counts": counts,
        "top_high_risk": [
            {
                "clause_id": c.clause_id,
                "clause_type": c.clause_type,
                "risk_reason": c.risk_reason,
                "text_preview": (c.clause_text[:220].replace("\n", " ") + "...") if len(c.clause_text) > 220 else c.clause_text,
            }
            for c in high_risk_sorted
        ],
        "red_flags": flags_out,
    }
