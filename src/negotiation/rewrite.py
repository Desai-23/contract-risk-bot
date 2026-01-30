from __future__ import annotations

import json
import re
from typing import Dict, Any, List
import requests

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL


_SYSTEM_PROMPT = """
You are a contract clause negotiation assistant for Indian SMEs.

Constraints:
- Do NOT provide legal advice.
- Provide general informational suggestions only.
- Use clear, business-friendly English.
- Output ONLY valid JSON (no markdown, no code fences).

Return JSON with EXACT keys:
- is_unfavorable (boolean)
- why_unfavorable (string)
- suggested_rewrite (string)
- negotiation_points (array of strings)
"""


def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"^\s*```json\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*```\s*", "", t)
    t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> str:
    t = text.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return t[start : end + 1].strip()


def rewrite_clause(clause_text: str, party_perspective: str = "SME") -> Dict[str, Any]:
    """
    Uses local Ollama model to:
      - classify if clause is unfavorable for SME
      - propose balanced SME-friendly rewrite
      - provide negotiation points
    """
    user_prompt = f"""
Assess if this clause is unfavorable to a small/medium business (SME).
If unfavorable, propose a balanced, SME-friendly rewrite (not one-sided).
Also list practical negotiation points.

Perspective: {party_perspective}

Clause:
\"\"\"
{clause_text}
\"\"\"
"""

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }

    r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180)
    r.raise_for_status()

    raw = r.json()["message"]["content"]
    cleaned = _strip_code_fences(raw)
    blob = _extract_json_object(cleaned)

    if not blob:
        return {
            "is_unfavorable": False,
            "why_unfavorable": "No JSON object found in model output.",
            "suggested_rewrite": cleaned,
            "negotiation_points": [],
        }

    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return {
            "is_unfavorable": False,
            "why_unfavorable": "Model output was not valid JSON.",
            "suggested_rewrite": cleaned,
            "negotiation_points": [],
        }

    # Normalize keys defensively
    negotiation_points = data.get("negotiation_points", [])
    if not isinstance(negotiation_points, list):
        negotiation_points = []

    return {
        "is_unfavorable": bool(data.get("is_unfavorable", False)),
        "why_unfavorable": str(data.get("why_unfavorable", "") or ""),
        "suggested_rewrite": str(data.get("suggested_rewrite", "") or ""),
        "negotiation_points": [str(x) for x in negotiation_points if str(x).strip()],
    }



