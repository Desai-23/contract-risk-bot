from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from langdetect import detect, LangDetectException

from src.nlp.normalize import normalize_contract_text


@dataclass
class Clause:
    clause_id: str
    text: str


@dataclass
class PreprocessResult:
    language: str                # detected source language: en|hi|unknown
    normalized_language: str     # always "en" after normalization
    did_normalize: bool
    normalized_text: str         # english text used for NLP
    clauses: List[Clause]


def detect_language(text: str) -> str:
    """
    Detect language using langdetect.
    Returns: "en", "hi", or "unknown"
    """
    try:
        lang = detect(text)
        if lang in {"en", "hi"}:
            return lang
        return "unknown"
    except LangDetectException:
        return "unknown"


def normalize_text(text: str) -> str:
    """
    Conservative normalization for clause splitting.
    Avoid aggressive cleanup because legal meaning can change.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)       # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)    # collapse big gaps
    return text.strip()


_CLAUSE_SPLIT_PATTERNS = [
    # Numbered clauses: "1.", "1.1", "2.3.4"
    r"(?m)^\s*(\d+(\.\d+){0,4})\s*[.)-]\s+",
    # Letter clauses: "a)", "b)"
    r"(?m)^\s*([a-zA-Z])\s*[.)-]\s+",
    # Common headings in contracts (English)
    r"(?m)^\s*(TERM|TERMINATION|PAYMENT|CONFIDENTIALITY|LIABILITY|INDEMNITY|GOVERNING LAW|JURISDICTION|ARBITRATION)\s*[:\-]?\s*$",
    # Hindi heading markers (basic)
    r"(?m)^\s*(अवधि|समाप्ति|भुगतान|गोपनीयता|दायित्व|क्षतिपूर्ति|शासन कानून|क्षेत्राधिकार|मध्यस्थता)\s*[:\-]?\s*$",
]


def extract_clauses(text: str) -> List[Clause]:
    """
    Rule-based clause segmentation.
    Runs on normalized English text (or original English).
    """
    norm = normalize_text(text)

    # Identify clause starts
    starts = []
    for pat in _CLAUSE_SPLIT_PATTERNS:
        for m in re.finditer(pat, norm):
            starts.append(m.start())

    starts = sorted(set(starts))

    # Fallback: paragraph splitting if no starts found
    if not starts:
        paras = [p.strip() for p in norm.split("\n\n") if p.strip()]
        out = []
        for i, p in enumerate(paras, start=1):
            out.append(Clause(clause_id=f"C{i:03d}", text=p))
        return out

    # Segment based on start indices
    segments = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(norm)
        chunk = norm[s:e].strip()
        if chunk:
            segments.append(chunk)

    clauses = []
    for i, seg in enumerate(segments, start=1):
        clauses.append(Clause(clause_id=f"C{i:03d}", text=seg))

    return clauses


def preprocess_contract(text: str) -> PreprocessResult:
    """
    Pipeline:
      1) detect language
      2) if Hindi -> translate to English (local Ollama)
      3) normalize + clause split on English text
    """
    lang = detect_language(text)

    # Hindi → English normalization
    norm_result = normalize_contract_text(text, lang)

    norm_text = normalize_text(norm_result.normalized_text)
    clauses = extract_clauses(norm_text)

    return PreprocessResult(
        language=lang,
        normalized_language=norm_result.normalized_language,
        did_normalize=norm_result.did_normalize,
        normalized_text=norm_text,
        clauses=clauses,
    )


