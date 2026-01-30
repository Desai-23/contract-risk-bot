from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import re

# High-signal patterns for selecting clauses for LLM semantic analysis
SELECT_PATTERNS: List[Tuple[str, int, re.Pattern]] = [
    ("Indemnity", 5, re.compile(r"\bindemnif(y|ies|ication)\b|\bhold harmless\b", re.I)),
    ("Penalty/Liquidated Damages", 5, re.compile(r"\b(liquidated damages|penalt(y|ies))\b", re.I)),
    ("Termination", 5, re.compile(r"\bterminate|termination|without cause|sole discretion|immediate effect\b", re.I)),
    ("Liability", 5, re.compile(r"\bliability\b|\bunlimited\b|\bcap\b|\blimit of liability\b", re.I)),
    ("Jurisdiction/Governing Law", 4, re.compile(r"\b(governing law|jurisdiction|courts? of|exclusive jurisdiction)\b", re.I)),
    ("Arbitration", 3, re.compile(r"\barbitration\b|\bseat\b|\brules\b", re.I)),
    ("Auto-Renewal", 4, re.compile(r"\b(auto[- ]?renew|automatically renew|renewal)\b", re.I)),
    ("Lock-in/Commitment", 5, re.compile(r"\b(lock[- ]?in|min(imum)? commitment|non[- ]?cancellable)\b", re.I)),
    ("Non-Compete", 5, re.compile(r"\b(non[- ]?compete|restraint of trade)\b", re.I)),
    ("IP Assignment/Transfer", 5, re.compile(r"\b(intellectual property|IP)\b.*\b(assign|assignment|transfer)\b", re.I)),
    ("Confidentiality/NDA", 2, re.compile(r"\b(confidential|non[- ]?disclosure|NDA)\b", re.I)),
    ("Payment", 2, re.compile(r"\b(payment|fees?|invoice|late fee|interest)\b", re.I)),
    ("Scope/Deliverables", 1, re.compile(r"\b(scope|deliverables?|milestone|SLA|service levels?)\b", re.I)),
    ("Term/Duration", 1, re.compile(r"\b(term|duration|commence|effective date)\b", re.I)),
]


@dataclass
class SelectedClause:
    clause_id: str
    text: str
    score: int
    reasons: List[str]


def score_clause(text: str) -> Tuple[int, List[str]]:
    """
    Returns (score, reasons) for clause selection.
    Higher score => more important to send to LLM.
    """
    score = 0
    reasons: List[str] = []
    t = text or ""

    for label, weight, pattern in SELECT_PATTERNS:
        if pattern.search(t):
            score += weight
            reasons.append(label)

    return score, reasons


def smart_select_clauses(
    clauses_list: List[Dict[str, Any]],
    max_llm_clauses: int = 12,
    ensure_baseline: int = 2,
) -> Tuple[List[SelectedClause], Dict[str, Any]]:
    """
    Selects clauses for LLM:
      - rank by selection score
      - include baseline first few clauses (ensure_baseline) for context
      - return selected clauses + debug stats

    clauses_list input format:
      [{"clause_id": "...", "text": "..."}, ...]
    """

    scored: List[SelectedClause] = []
    for c in clauses_list:
        s, reasons = score_clause(c.get("text", ""))
        scored.append(
            SelectedClause(
                clause_id=c.get("clause_id", ""),
                text=c.get("text", ""),
                score=s,
                reasons=reasons,
            )
        )

    # Baseline clauses (first N) always included
    baseline = scored[: max(0, ensure_baseline)]

    # Rank all clauses by score desc, then length desc (tie-breaker)
    ranked = sorted(
        scored,
        key=lambda x: (x.score, len(x.text)),
        reverse=True,
    )

    selected: List[SelectedClause] = []
    seen_ids = set()

    # Add baseline first
    for c in baseline:
        if c.clause_id and c.clause_id not in seen_ids:
            selected.append(c)
            seen_ids.add(c.clause_id)

    # Add ranked high-signal clauses
    for c in ranked:
        if len(selected) >= max_llm_clauses:
            break
        if c.clause_id and c.clause_id not in seen_ids:
            # Only include if it has some signal OR we still need to fill slots
            if c.score > 0 or len(selected) < max_llm_clauses:
                selected.append(c)
                seen_ids.add(c.clause_id)

    stats = {
        "total_clauses": len(clauses_list),
        "selected_for_llm": len(selected),
        "max_llm_clauses": max_llm_clauses,
        "baseline_included": len(baseline),
        "top_scores": sorted({c.score for c in selected}, reverse=True)[:5],
    }

    return selected, stats

