from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Any

from langdetect import detect, LangDetectException

from src.nlp.normalize import normalize_contract_text
from src.nlp.contract_type import classify_contract_type
from src.nlp.entities import extract_entities
from src.nlp.deontic import extract_deontic_statements
from src.nlp.ambiguity import detect_ambiguity


@dataclass
class Clause:
    clause_id: str
    text: str


@dataclass
class PreprocessResult:
    # Language normalization
    language: str
    normalized_language: str
    did_normalize: bool
    normalized_text: str

    # Clause extraction
    clauses: List[Clause]

    # Contract type classification
    contract_type: str
    contract_type_confidence: float
    contract_type_method: str
    contract_type_evidence: List[str]

    # Named entities
    entities: Dict[str, Any]

    # NEW: Obligation/Right/Prohibition extraction
    deontic: Dict[str, Any]

    ambiguity: Dict[str, Any]



def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        if lang in {"en", "hi"}:
            return lang
        return "unknown"
    except LangDetectException:
        return "unknown"


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_CLAUSE_SPLIT_PATTERNS = [
    r"(?m)^\s*(\d+(\.\d+){0,4})\s*[.)-]\s+",
    r"(?m)^\s*([a-zA-Z])\s*[.)-]\s+",
    r"(?m)^\s*(TERM|TERMINATION|PAYMENT|CONFIDENTIALITY|LIABILITY|INDEMNITY|GOVERNING LAW|JURISDICTION|ARBITRATION)\s*[:\-]?\s*$",
    r"(?m)^\s*(अवधि|समाप्ति|भुगतान|गोपनीयता|दायित्व|क्षतिपूर्ति|शासन कानून|क्षेत्राधिकार|मध्यस्थता)\s*[:\-]?\s*$",
]


def extract_clauses(text: str) -> List[Clause]:
    norm = normalize_text(text)

    starts = []
    for pat in _CLAUSE_SPLIT_PATTERNS:
        for m in re.finditer(pat, norm):
            starts.append(m.start())

    starts = sorted(set(starts))

    if not starts:
        paras = [p.strip() for p in norm.split("\n\n") if p.strip()]
        return [Clause(clause_id=f"C{i:03d}", text=p) for i, p in enumerate(paras, start=1)]

    segments = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(norm)
        chunk = norm[s:e].strip()
        if chunk:
            segments.append(chunk)

    return [Clause(clause_id=f"C{i:03d}", text=seg) for i, seg in enumerate(segments, start=1)]


def preprocess_contract(text: str) -> PreprocessResult:
    lang = detect_language(text)

    # Hindi → English normalization
    norm_result = normalize_contract_text(text, lang)
    norm_text = normalize_text(norm_result.normalized_text)

    # Contract type classification on normalized English
    ct = classify_contract_type(norm_text, llm_fallback_threshold=0.55)




    # Named entity extraction
    entities = extract_entities(norm_text)

    ambiguity = detect_ambiguity(norm_text)


    # Obligation / right / prohibition extraction
    deontic = extract_deontic_statements(norm_text)

    # Clause extraction
    clauses = extract_clauses(norm_text)

    return PreprocessResult(
        language=lang,
        normalized_language=norm_result.normalized_language,
        did_normalize=norm_result.did_normalize,
        normalized_text=norm_text,
        clauses=clauses,
        contract_type=ct.contract_type,
        contract_type_confidence=ct.confidence,
        contract_type_method=ct.method,
        contract_type_evidence=ct.evidence,
        entities=entities,
        deontic=deontic,
        ambiguity=ambiguity
    )
