from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple


KB_PATH = Path("data/knowledge_base/contract_insights.jsonl")


def _ensure_kb_path():
    KB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not KB_PATH.exists():
        KB_PATH.write_text("", encoding="utf-8")


def _parse_contract_type(contract_type_line: str) -> str:
    if not contract_type_line:
        return "unknown"
    return (contract_type_line.split("|")[0].strip() or "unknown")


def _extract_ambiguity_level(ambiguity_text: str) -> str:
    if not ambiguity_text:
        return "Unknown"
    first = ambiguity_text.splitlines()[0].strip()
    if "Ambiguity Level:" in first:
        return first.replace("Ambiguity Level:", "").strip()
    return "Unknown"


def _count_compliance_flags(compliance_text: str) -> int:
    if not compliance_text or "No compliance" in compliance_text:
        return 0
    return sum(1 for line in compliance_text.splitlines() if line.strip().startswith("- ["))


def _parse_red_flag_types(red_flags_text: str) -> List[str]:
    """
    red_flags_text looks like:
      - [High] UNILATERAL_TERMINATION: reason...
    We'll extract the flag type between bracket and colon.
    """
    out = []
    if not red_flags_text or "No rule-based red flags" in red_flags_text:
        return out

    for line in red_flags_text.splitlines():
        line = line.strip()
        if not line.startswith("- ["):
            continue
        # try to extract between "] " and ":"
        try:
            after = line.split("] ", 1)[1]
            flag_type = after.split(":", 1)[0].strip()
            if flag_type:
                out.append(flag_type)
        except Exception:
            continue
    return out


def _parse_top_clause_types(top_high_risk_text: str) -> List[str]:
    """
    top_high_risk_text first lines look like:
      - C001 (Indemnity): ...
    We'll extract what's inside parentheses.
    """
    out = []
    if not top_high_risk_text or "No High-risk clauses" in top_high_risk_text:
        return out

    for block in top_high_risk_text.split("\n\n"):
        blk = block.strip()
        if not blk.startswith("- "):
            continue
        # "- C001 (Indemnity): ..."
        try:
            left = blk.split("\n", 1)[0]
            if "(" in left and ")" in left:
                inside = left.split("(", 1)[1].split(")", 1)[0].strip()
                if inside:
                    out.append(inside)
        except Exception:
            continue
    return out


def append_contract_insight(
    contract_type_line: str,
    overall_risk: str,
    avg_score: str,
    ambiguity_text: str,
    red_flags_text: str,
    compliance_text: str,
    top_high_risk_text: str,
) -> Dict[str, Any]:
    """
    Stores a single derived insight record into JSONL.
    IMPORTANT: We do NOT store raw contract text.
    """
    _ensure_kb_path()

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "contract_type": _parse_contract_type(contract_type_line),
        "overall_risk": str(overall_risk or "Unclear"),
        "avg_score": str(avg_score or "0.0"),
        "ambiguity_level": _extract_ambiguity_level(ambiguity_text),
        "compliance_flags_count": _count_compliance_flags(compliance_text),
        "red_flag_types": _parse_red_flag_types(red_flags_text),
        "top_clause_types": _parse_top_clause_types(top_high_risk_text),
    }

    with open(KB_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record


def _read_last_n(n: int = 200) -> List[Dict[str, Any]]:
    _ensure_kb_path()
    lines = KB_PATH.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if ln.strip()]
    tail = lines[-n:] if n and len(lines) > n else lines
    out = []
    for ln in tail:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _count(items: List[str]) -> List[Tuple[str, int]]:
    m: Dict[str, int] = {}
    for x in items:
        x = str(x).strip()
        if not x:
            continue
        m[x] = m.get(x, 0) + 1
    return sorted(m.items(), key=lambda t: t[1], reverse=True)


def get_kb_dashboard(n: int = 200) -> Dict[str, Any]:
    rows = _read_last_n(n=n)

    if not rows:
        return {
            "records": 0,
            "message": "Knowledge base is empty. Run 'Analyze Full Contract' to populate it."
        }

    contract_types = [r.get("contract_type", "unknown") for r in rows]
    risk_levels = [r.get("overall_risk", "Unclear") for r in rows]
    ambiguity_levels = [r.get("ambiguity_level", "Unknown") for r in rows]

    all_flags = []
    all_clause_types = []
    compliance_counts = []

    for r in rows:
        all_flags.extend(r.get("red_flag_types", []) or [])
        all_clause_types.extend(r.get("top_clause_types", []) or [])
        compliance_counts.append(int(r.get("compliance_flags_count", 0) or 0))

    top_flags = _count(all_flags)[:10]
    top_clause_types = _count(all_clause_types)[:10]

    avg_compliance_flags = round(sum(compliance_counts) / max(1, len(compliance_counts)), 2)

    return {
        "records": len(rows),
        "last_n_window": n,
        "contract_type_distribution": _count(contract_types),
        "overall_risk_distribution": _count(risk_levels),
        "ambiguity_distribution": _count(ambiguity_levels),
        "top_red_flags": top_flags,
        "top_high_risk_clause_types": top_clause_types,
        "avg_compliance_flags_count": avg_compliance_flags,
        "latest_record": rows[-1],
    }
