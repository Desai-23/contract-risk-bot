from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ComplianceFlag:
    topic: str
    severity: str  # Low | Medium | High
    why_flagged: str
    what_to_check: List[str]


# Heuristic checks only. No external legal DB/statutes. Not legal advice.
CHECKS: List[Tuple[str, str, re.Pattern, str, List[str]]] = [
    (
        "Non-Compete / Restraint of Trade",
        "High",
        re.compile(r"\b(non[- ]?compete|restraint of trade)\b", re.I),
        "Non-compete restrictions can create enforceability and operational risk for Indian SMEs.",
        [
            "Check if scope, duration, and geography are limited and reasonable.",
            "Prefer NDA + non-solicit instead of broad non-compete where possible.",
            "Ensure restrictions are tied to legitimate interests (confidentiality/IP).",
        ],
    ),
    (
        "Foreign Governing Law / Jurisdiction",
        "High",
        re.compile(
            r"\b(governed by the laws of|governing law)\b.*\b(england|uk|united states|usa|delaware|singapore|uae|dubai)\b",
            re.I,
        ),
        "Foreign law/jurisdiction can increase cost/complexity for an India-based SME.",
        [
            "Confirm why foreign law is required; attempt Indian law if possible.",
            "Assess practical cost of disputes outside India (travel, counsel, enforcement).",
            "Consider adding India jurisdiction or an India arbitration seat.",
        ],
    ),
    (
        "Arbitration Seat Outside India",
        "Medium",
        re.compile(r"\b(arbitration)\b.*\b(seat|seated in)\b.*\b(london|singapore|new york|dubai)\b", re.I),
        "Foreign arbitration seat may increase cost and operational friction.",
        [
            "Check seat, rules, language, and fee allocation.",
            "Consider an India seat (Mumbai/Delhi) for practicality.",
            "Confirm interim relief and enforcement options are acceptable.",
        ],
    ),
    (
        "Unlimited Liability / No Cap",
        "High",
        re.compile(r"\b(unlimited liability|liability shall be unlimited|without any maximum cap|no cap)\b", re.I),
        "Unlimited liability may create unbounded financial exposure; SMEs typically require caps.",
        [
            "Negotiate a liability cap (e.g., fees paid in last 3–12 months).",
            "Limit carve-outs to narrow categories (fraud/willful misconduct).",
            "Exclude or cap indirect/consequential damages where possible.",
        ],
    ),
    (
        "Auto-Renewal",
        "Medium",
        re.compile(r"\b(auto[- ]?renew|automatically renew|renewal)\b", re.I),
        "Auto-renewal can lead to unintended renewals if notice windows are missed.",
        [
            "Check notice period and set calendar reminders.",
            "Ask for explicit renewal confirmation instead of automatic renewal.",
            "Control pricing changes at renewal and include termination window.",
        ],
    ),
    (
        "Data Handling / Privacy (Indicative)",
        "Medium",
        re.compile(r"\b(personal data|sensitive personal|data protection|privacy|data processing)\b", re.I),
        "If personal data is processed, ensure roles, safeguards, and breach obligations are clear.",
        [
            "Confirm what data is collected and the purpose limitation.",
            "Ensure security controls, breach notification, deletion/return are defined.",
            "Clarify subcontractor access and cross-border transfer terms, if any.",
        ],
    ),
    (
        "IP Assignment / Transfer",
        "Medium",
        re.compile(r"\b(intellectual property|IP)\b.*\b(assign|assignment|transfer)\b", re.I),
        "Broad IP transfer may unintentionally transfer background IP or reusable components.",
        [
            "Separate background IP vs deliverables IP.",
            "Add license-back if vendor needs reusable components.",
            "Clarify ownership of pre-existing templates/tools/know-how.",
        ],
    ),
]


def run_compliance_checks(full_text: str) -> List[ComplianceFlag]:
    text = full_text or ""
    flags: List[ComplianceFlag] = []
    for topic, severity, pattern, why, checklist in CHECKS:
        if pattern.search(text):
            flags.append(
                ComplianceFlag(
                    topic=topic,
                    severity=severity,
                    why_flagged=why,
                    what_to_check=checklist,
                )
            )
    return flags


def format_compliance_flags(flags: List[ComplianceFlag]) -> str:
    if not flags:
        return "No compliance-related heuristic flags detected."

    lines: List[str] = []
    for f in flags:
        lines.append(f"- [{f.severity}] {f.topic}")
        lines.append(f"  Why flagged: {f.why_flagged}")
        lines.append("  What to check:")
        for item in f.what_to_check:
            lines.append(f"   • {item}")
        lines.append("")  # spacing
    return "\n".join(lines).strip()

