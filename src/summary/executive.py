from __future__ import annotations

from typing import Dict, Any, List


def _take(items: List[str], n: int = 3) -> List[str]:
    items = items or []
    out = []
    seen = set()
    for x in items:
        s = str(x).strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
        if len(out) >= n:
            break
    return out


def _safe_join(items: List[str]) -> str:
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    return ", ".join(items) if items else "Not found"


def generate_executive_summary(
    contract_type_line: str,
    entities: Dict[str, Any],
    ambiguity_text: str,
    overall_risk: str,
    avg_score: str,
    top_high_risk_text: str,
    red_flags_text: str,
    compliance_text: str,
) -> str:
    """
    Generates a plain-English executive summary for SME founders.
    Inputs are taken directly from existing UI/components.
    """

    ctype = "unknown"
    if contract_type_line:
        ctype = contract_type_line.split("|")[0].strip() or "unknown"

    parties = (entities or {}).get("parties", {}) or {}
    roles = parties.get("roles", {}) or {}
    orgs = _take((entities or {}).get("organizations", []), 4)

    party_lines = []
    if roles:
        for k, v in roles.items():
            party_lines.append(f"- {k.title()}: {v}")
    else:
        party_lines.append(f"- Organizations (detected): {_safe_join(orgs)}")

    dates = _take((entities or {}).get("dates", []), 4)
    money = _take((entities or {}).get("money_amounts", []), 4)
    juris = _take((entities or {}).get("jurisdiction_mentions", []), 3)

    # Clean red flags lines
    rf_lines = []
    if red_flags_text and "No rule-based red flags" not in red_flags_text:
        for line in red_flags_text.splitlines():
            line = line.strip()
            if line.startswith("- "):
                rf_lines.append(line)
    rf_lines = rf_lines[:6]

    # Summarize top high risk clauses (already formatted)
    thr_lines = []
    if top_high_risk_text and "No High-risk clauses" not in top_high_risk_text:
        for block in top_high_risk_text.split("\n\n"):
            blk = block.strip()
            if blk.startswith("- "):
                thr_lines.append(blk.split("\n")[0])  # only first line
    thr_lines = thr_lines[:5]

    # Ambiguity level extraction from first line if available
    amb_level = "Unknown"
    if ambiguity_text:
        first = ambiguity_text.splitlines()[0].strip()
        if "Ambiguity Level:" in first:
            amb_level = first.replace("Ambiguity Level:", "").strip()

    # Compliance quick count
    compliance_count = 0
    if compliance_text and "No compliance-related" not in compliance_text:
        compliance_count = sum(1 for line in compliance_text.splitlines() if line.strip().startswith("- ["))

    actions = [
        "Review the top high-risk clauses and renegotiate the highlighted points.",
        "Ensure termination, liability cap, and indemnity are balanced and capped.",
        "Confirm governing law/jurisdiction and dispute resolution are practical for your business.",
        "Replace ambiguous terms (e.g., 'reasonable', 'sole discretion') with measurable definitions and timelines.",
        "Export the report and share with a legal professional for final validation (not legal advice).",
    ]

    summary = []
    summary.append("EXECUTIVE SUMMARY (SME-FRIENDLY)")
    summary.append("")
    summary.append(f"Contract Type (predicted): {ctype}")
    summary.append(f"Overall Risk: {overall_risk} | Avg Risk Score: {avg_score}")
    summary.append(f"Ambiguity: {amb_level}")
    summary.append(f"Compliance Flags (heuristics): {compliance_count}")
    summary.append("")
    summary.append("Key Parties:")
    summary.extend(party_lines)
    summary.append("")
    summary.append(f"Key Dates (detected): {_safe_join(dates)}")
    summary.append(f"Key Amounts (detected): {_safe_join(money)}")
    summary.append(f"Jurisdiction / Governing Law mentions: {_safe_join(juris)}")
    summary.append("")
    summary.append("Top High-Risk Clauses (subset analyzed):")
    if thr_lines:
        for x in thr_lines:
            summary.append(f"- {x[2:] if x.startswith('- ') else x}")
    else:
        summary.append("- None detected in analyzed subset.")
    summary.append("")
    summary.append("Red Flags (rule-based):")
    if rf_lines:
        summary.extend(rf_lines)
    else:
        summary.append("- None detected.")
    summary.append("")
    summary.append("Recommended Next Actions:")
    for a in actions:
        summary.append(f"- {a}")

    return "\n".join(summary).strip()
