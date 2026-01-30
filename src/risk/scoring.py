from typing import Dict, Any


def normalize_risk(llm_result: Dict[str, Any]) -> Dict[str, Any]:
    risk = llm_result.get("risk_level", "Unclear")
    if risk not in {"Low", "Medium", "High"}:
        risk = "Unclear"

    return {
        "clause_type": llm_result.get("clause_type", "Unknown"),
        "explanation": llm_result.get("explanation", ""),
        "risk_level": risk,
        "risk_reason": llm_result.get("risk_reason", ""),
        "mitigation": llm_result.get("mitigation_suggestion", ""),
    }

