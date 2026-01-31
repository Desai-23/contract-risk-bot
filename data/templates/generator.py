from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, List

TEMPLATE_PATH = Path("data/templates/sme_contracts.json")


def load_contract_templates() -> Dict[str, Any]:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Contract template file not found: {TEMPLATE_PATH}")
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def generate_contract(contract_type: str) -> Dict[str, Any]:
    """
    Returns:
      {
        "contract_type": str,
        "name": str,
        "description": str,
        "text": str
      }
    """
    data = load_contract_templates()
    contracts = data.get("contracts", [])

    for c in contracts:
        if c.get("contract_type") == contract_type:
            sections = []
            for clause in c.get("clauses", []):
                sections.append(f"{clause['title']}\n{clause['text']}")
            full_text = "\n\n".join(sections)

            return {
                "contract_type": contract_type,
                "name": c.get("name"),
                "description": c.get("description"),
                "text": full_text,
            }

    raise ValueError(f"No SME template found for contract type: {contract_type}")
