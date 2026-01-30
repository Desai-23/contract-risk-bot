from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Dict, Any

from langdetect import detect, LangDetectException


@dataclass
class Clause:
    clause_id: str
    text: str


@dataclass
class PreprocessResult:
    language: str          # "en" | "hi" | "unknown"
    normalized_text: str   # currently same as input; later we can normalize Hindi→English
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
    Basic normalization for clause splitting.
    (We keep it conservative to avoid destroying legal meaning.)
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)       # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)    # collapse large blank gaps
    return text.strip()


_CLAUSE_SPLIT_PATTERNS = [
    # Numbered clauses: "1.", "1.1", "2.3.4"
    r"(?m)^\s*(\d+(\.\d+){0,4})\s*[.)-]\s+",
    # Letter clauses: "a)", "b)"
    r"(?m)^\s*([a-zA-Z])\s*[.)-]\s+",
    # Common headings in contracts
    r"(?m)^\s*(TERM|TERMINATION|PAYMENT|CONFIDENTIALITY|LIABILITY|INDEMNITY|GOVERNING LAW|JURISDICTION|ARBITRATION)\s*[:\-]?\s*$",
    # Hindi heading markers (basic)
    r"(?m)^\s*(अवधि|समाप्ति|भुगतान|गोपनीयता|दायित्व|क्षतिपूर्ति|शासन कानून|क्षेत्राधिकार|मध्यस्थता)\s*[:\-]?\s*$",
]


def extract_clauses(text: str) -> List[Clause]:
    """
    Rule-based clause segmentation.
    This is not perfect; we refine it in later phases.
    """
    norm = normalize_text(text)

    # Build a unified regex that identifies clause starts
    starts = []
    for pat in _CLAUSE_SPLIT_PATTERNS:
        for m in re.finditer(pat, norm):
            starts.append(m.start())

    starts = sorted(set(starts))

    # If no starts found, fallback to paragraph splitting
    if not starts:
        paras = [p.strip() for p in norm.split("\n\n") if p.strip()]
        out = []
        for i, p in enumerate(paras, start=1):
            out.append(Clause(clause_id=f"C{i:03d}", text=p))
        return out

    # Segment using detected clause starts
    segments = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(norm)
        chunk = norm[s:e].strip()
        if chunk:
            segments.append(chunk)

    # Assign IDs
    clauses = []
    for i, seg in enumerate(segments, start=1):
        clauses.append(Clause(clause_id=f"C{i:03d}", text=seg))

    return clauses


def preprocess_contract(text: str) -> PreprocessResult:
    lang = detect_language(text)
    norm = normalize_text(text)
    clauses = extract_clauses(norm)

    return PreprocessResult(
        language=lang,
        normalized_text=norm,
        clauses=clauses,
    )

