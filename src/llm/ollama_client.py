from __future__ import annotations

import json
import re
from typing import Dict, Any
import requests

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL


SYSTEM_PROMPT = """
You are a contract clause analysis engine for Indian SMEs.

Hard constraints:
- Output MUST be valid JSON only.
- Do NOT wrap output in markdown fences like ```json.
- Do NOT include commentary outside JSON.

Schema (exact keys):
{
  "clause_type": "...",
  "explanation": "...",
  "risk_level": "Low|Medium|High",
  "risk_reason": "...",
  "mitigation_suggestion": "..."
}
"""


def _strip_code_fences(text: str) -> str:
    """
    Removes markdown code fences if present.
    Handles: ```json ... ``` and ``` ... ```
    """
    t = text.strip()

    # Remove starting fence
    t = re.sub(r"^\s*```json\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*```\s*", "", t)

    # Remove ending fence
    t = re.sub(r"\s*```\s*$", "", t)

    return t.strip()


def _extract_json_object(text: str) -> str:
    """
    Extract JSON object substring from first '{' to last '}'.
    This is robust when the model adds leading/trailing text.
    """
    t = text.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return t[start : end + 1].strip()


def _normalize_keys(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    The model sometimes returns:
    - explain instead of explanation
    - risk_reason vs risk reason (rare)
    We normalize without breaking schema.
    """
    explanation = data.get("explanation")
    if not explanation:
        explanation = data.get("explain", "")

    risk_reason = data.get("risk_reason")
    if not risk_reason:
        risk_reason = data.get("risk reason", "")

    mitigation = data.get("mitigation_suggestion")
    if not mitigation:
        mitigation = data.get("mitigation suggestion", "")

    return {
        "clause_type": data.get("clause_type", "Unknown"),
        "explanation": explanation or "",
        "risk_level": data.get("risk_level", "Unclear"),
        "risk_reason": risk_reason or "",
        "mitigation_suggestion": mitigation or "",
    }


def analyze_clause_with_llm(clause_text: str) -> Dict[str, Any]:
    user_prompt = f"""
Analyze this contract clause and return ONLY JSON matching the schema.

Clause:
\"\"\"
{clause_text}
\"\"\"
"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
    r.raise_for_status()

    raw = r.json()["message"]["content"]

    # 1) Strip fences
    cleaned = _strip_code_fences(raw)

    # 2) Extract JSON object region
    json_blob = _extract_json_object(cleaned)
    if not json_blob:
        return {
            "clause_type": "Unknown",
            "explanation": cleaned,
            "risk_level": "Unclear",
            "risk_reason": "No JSON object found in model output (missing '{' or '}').",
            "mitigation_suggestion": "Review manually.",
        }

    # 3) Parse JSON
    try:
        parsed = json.loads(json_blob)
    except json.JSONDecodeError as e:
        return {
            "clause_type": "Unknown",
            "explanation": cleaned,
            "risk_level": "Unclear",
            "risk_reason": f"JSONDecodeError: {e}",
            "mitigation_suggestion": "Review manually.",
        }

    # 4) Normalize keys
    return _normalize_keys(parsed)
