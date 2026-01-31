from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

from rapidfuzz import fuzz


TEMPLATE_PATH = Path("data/templates/sme_templates.json")


@dataclass
class TemplateClause:
    id: str
    contract_types: List[str]
    category: str
    name: str
    text: str


def load_templates() -> List[TemplateClause]:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template library not found: {TEMPLATE_PATH}")

    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    out: List[TemplateClause] = []
    for t in data.get("templates", []):
        out.append(
            TemplateClause(
                id=str(t.get("id", "")),
                contract_types=list(t.get("contract_types", ["unknown"])),
                category=str(t.get("category", "unknown")),
                name=str(t.get("name", "")),
                text=str(t.get("text", "")),
            )
        )
    return out


def match_clause_to_templates(
    clause_text: str,
    contract_type: str = "unknown",
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Returns top_k matches by similarity.
    Uses fuzzy token_set_ratio (good for legal text).
    """
    clause_text = clause_text or ""
    templates = load_templates()

    scored = []
    for t in templates:
        # Contract type filter: allow "unknown" templates + matching types
        if contract_type not in (t.contract_types or ["unknown"]) and "unknown" not in (t.contract_types or []):
            continue

        score = fuzz.token_set_ratio(clause_text, t.text)  # 0-100
        scored.append((score, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:top_k]

    results = []
    for score, t in scored:
        results.append(
            {
                "template_id": t.id,
                "template_name": t.name,
                "category": t.category,
                "allowed_contract_types": t.contract_types,
                "similarity_score": int(score),
                "template_text": t.text,
            }
        )
    return results
