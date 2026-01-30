from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class RedFlag:
    flag_type: str
    severity: str  # "Low" | "Medium" | "High"
    reason: str


# Simple, auditable regex patterns (hackathon-safe)
PATTERNS: List[Tuple[str, str, re.Pattern, str]] = [
    # (flag_type, severity, regex, reason)
    ("Indemnity", "High", re.compile(r"\bindemnif(y|ies|ication)\b", re.I),
     "Indemnity shifts liability; check scope, exclusions, and caps."),
    ("Penalty/Liquidated Damages", "High", re.compile(r"\b(liquidated damages|penalt(y|ies))\b", re.I),
     "Penalty or liquidated damages may create large financial exposure."),
    ("Unilateral Termination", "High", re.compile(r"\b(terminate.*at any time|terminate.*without cause|sole discretion)\b", re.I),
     "One party may be able to terminate without balanced notice/conditions."),
    ("Arbitration", "Medium", re.compile(r"\barbitration\b", re.I),
     "Arbitration affects dispute resolution cost/time; check seat and rules."),
    ("Jurisdiction/Governing Law", "Medium", re.compile(r"\b(governing law|jurisdiction|courts? of)\b", re.I),
     "Jurisdiction can increase litigation cost if not local/acceptable."),
    ("Auto-Renewal", "Medium", re.compile(r"\b(auto[- ]?renew|automatically renew)\b", re.I),
     "Auto-renewal can lock you in unless notice is provided in time."),
    ("Lock-in/Minimum Commitment", "High", re.compile(r"\b(lock[- ]?in|min(imum)? commitment|non[- ]?cancellable)\b", re.I),
     "Lock-in periods reduce flexibility and can create unavoidable costs."),
    ("Non-Compete", "High", re.compile(r"\b(non[- ]?compete|restraint of trade)\b", re.I),
     "Non-compete limits future business options; check scope/duration/territory."),
    ("IP Assignment/Transfer", "High", re.compile(r"\b(assign(s|ment)?|transfer)\b.*\b(intellectual property|IP)\b", re.I),
     "IP assignment may transfer ownership; confirm what you retain."),
    ("Confidentiality/NDA", "Low", re.compile(r"\b(confidential|non[- ]?disclosure|NDA)\b", re.I),
     "Confidentiality is common; check duration and permitted disclosures."),
]


def detect_red_flags(text: str) -> List[RedFlag]:
    """
    Rule-based detection of red flags.
    Works for English text (Hindi handled later by normalization phase).
    """
    flags: List[RedFlag] = []
    for flag_type, severity, pattern, reason in PATTERNS:
        if pattern.search(text or ""):
            flags.append(RedFlag(flag_type=flag_type, severity=severity, reason=reason))
    return flags
