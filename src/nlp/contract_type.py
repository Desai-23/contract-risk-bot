from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple

import requests

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL


CONTRACT_TYPES = [
    "employment_agreement",
    "vendor_contract",
    "lease_agreement",
    "partnership_deed",
    "service_contract",
    "unknown",
]

# Rule-based keyword buckets (auditable & fast)
RULE_SETS: Dict[str, List[str]] = {
    "employment_agreement": [
        "employee", "employer", "employment", "salary", "wages", "probation",
        "notice period", "termination", "hr", "designation", "work hours",
        "confidentiality", "non-compete", "non solicitation", "leave", "appraisal",
        "ctc", "joining", "offer letter",
    ],
    "vendor_contract": [
        "vendor", "purchase order", "po", "supply", "goods", "delivery",
        "acceptance", "invoice", "quality", "inspection", "warranty",
        "indemnity", "penalty", "liquidated damages", "service levels",
        "client", "supplier",
    ],
    "lease_agreement": [
        "lease", "rent", "landlord", "tenant", "premises", "security deposit",
        "maintenance", "possession", "eviction", "utility", "lock-in",
        "renewal", "rent escalation", "fit-out", "termination of lease",
    ],
    "partnership_deed": [
        "partnership", "partner", "profit sharing", "capital contribution",
        "drawings", "firm", "partnership deed", "dissolution", "accounts",
        "admission of partner", "retirement", "indemnify partners",
    ],
    "service_contract": [
        "services", "statement of work", "sow", "scope of work", "deliverables",
        "milestone", "sla", "support", "maintenance", "professional services",
        "fees", "payment terms", "termination", "confidentiality",
    ],
}

# Some regex patterns that strongly indicate a type
STRONG_PATTERNS: List[Tuple[str, re.Pattern, int]] = [
    ("employment_agreement", re.compile(r"\b(offer letter|appointment letter|employment agreement)\b", re.I), 6),
    ("lease_agreement", re.compile(r"\b(lease agreement|rent agreement|lessor|lessee)\b", re.I), 6),
    ("partnership_deed", re.compile(r"\b(partnership deed|partners? hereby agree)\b", re.I), 6),
    ("vendor_contract", re.compile(r"\b(purchase order|supplier|supply of goods)\b", re.I), 5),
    ("service_contract", re.compile(r"\b(statement of work|scope of services|service agreement)\b", re.I), 5),
]


@dataclass
class ContractTypeResult:
    contract_type: str
    confidence: float          # 0.0 - 1.0
    method: str                # "rules" | "llm"
    evidence: List[str]        # short evidence strings


def _token_score(text: str, tokens: List[str]) -> int:
    t = text.lower()
    score = 0
    for tok in tokens:
        if tok.lower() in t:
            score += 1
    return score


def _rules_classify(text: str) -> ContractTypeResult:
    """
    Rule-based classifier:
      - scores each contract type using keyword hits + strong patterns
      - converts into a confidence score
    """
    t = text or ""
    evidence: Dict[str, List[str]] = {k: [] for k in RULE_SETS.keys()}
    scores: Dict[str, int] = {k: 0 for k in RULE_SETS.keys()}

    # Strong pattern boosts
    for ctype, pattern, boost in STRONG_PATTERNS:
        if pattern.search(t):
            scores[ctype] += boost
            evidence[ctype].append(f"pattern:{pattern.pattern}")

    # Keyword scoring
    for ctype, toks in RULE_SETS.items():
        s = _token_score(t, toks)
        scores[ctype] += s
        if s > 0:
            # Add only a few evidence tokens (avoid dumping everything)
            hit_tokens = [tok for tok in toks if tok.lower() in t.lower()][:5]
            evidence[ctype].extend([f"kw:{x}" for x in hit_tokens])

    # Pick best
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_type, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    # Confidence heuristic:
    # - depends on score magnitude and separation from runner-up
    if best_score <= 1:
        confidence = 0.30
    else:
        separation = best_score - second_score
        confidence = min(0.95, 0.45 + (best_score / 20.0) + (separation / 10.0))

    ev = evidence.get(best_type, [])[:6]
    return ContractTypeResult(contract_type=best_type, confidence=round(confidence, 2), method="rules", evidence=ev)


def _strip_code_fences(text: str) -> str:
    txt = (text or "").strip()
    txt = re.sub(r"^\s*```json\s*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"^\s*```\s*", "", txt)
    txt = re.sub(r"\s*```\s*$", "", txt)
    return txt.strip()


def _extract_json_object(text: str) -> str:
    t = text.strip()
    s = t.find("{")
    e = t.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return ""
    return t[s : e + 1].strip()


def _llm_classify(text: str) -> ContractTypeResult:
    """
    LLM fallback via local Ollama.
    Must output JSON only.
    """
    system = f"""
You are a contract type classifier for Indian SME contracts.
Return ONLY valid JSON. No markdown.

Allowed contract_type values: {CONTRACT_TYPES}

JSON schema:
{{
  "contract_type": "employment_agreement|vendor_contract|lease_agreement|partnership_deed|service_contract|unknown",
  "confidence": 0.0,
  "evidence": ["short strings"]
}}
"""
    # Keep prompt small; send first ~6000 chars for speed
    snippet = (text or "")[:6000]

    user = f"""
Classify the contract type using the allowed values only.
Text:
\"\"\"
{snippet}
\"\"\"
"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
    r.raise_for_status()

    raw = r.json()["message"]["content"]
    cleaned = _strip_code_fences(raw)
    blob = _extract_json_object(cleaned)

    if not blob:
        return ContractTypeResult(contract_type="unknown", confidence=0.0, method="llm", evidence=["llm:no_json"])

    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return ContractTypeResult(contract_type="unknown", confidence=0.0, method="llm", evidence=["llm:bad_json"])

    ctype = data.get("contract_type", "unknown")
    if ctype not in CONTRACT_TYPES:
        ctype = "unknown"

    conf = data.get("confidence", 0.0)
    try:
        conf = float(conf)
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    ev = data.get("evidence", [])
    if not isinstance(ev, list):
        ev = []
    ev = [str(x) for x in ev][:6]

    return ContractTypeResult(contract_type=ctype, confidence=round(conf, 2), method="llm", evidence=ev)


def classify_contract_type(text: str, llm_fallback_threshold: float = 0.55) -> ContractTypeResult:
    """
    1) rule-based classification
    2) if confidence < threshold -> LLM fallback
    """
    rules_res = _rules_classify(text)

    if rules_res.confidence >= llm_fallback_threshold:
        return rules_res

    llm_res = _llm_classify(text)
    # If LLM produces nonsense, keep rules result
    if llm_res.contract_type == "unknown" and rules_res.contract_type != "unknown":
        return rules_res
    return llm_res
