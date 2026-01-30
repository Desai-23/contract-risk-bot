from __future__ import annotations

import re
from dataclasses import dataclass
import requests

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL


@dataclass
class NormalizationResult:
    original_language: str   # "en" | "hi" | "unknown"
    normalized_language: str # always "en"
    did_normalize: bool
    normalized_text: str


_TRANSLATION_SYSTEM_PROMPT = """
You are a translation engine.
Translate Hindi contract text to clear, professional English.

Hard constraints:
- Output ONLY English plain text.
- Do NOT output JSON.
- Do NOT output markdown or code fences.
- Preserve clause numbering, headings, and formatting as much as possible.
- Do NOT add new content. Do NOT provide legal advice.
"""


def _cleanup_translation(text: str) -> str:
    """
    Removes accidental formatting like markdown code fences.
    """
    t = (text or "").strip()

    # Remove starting ``` or ```json fences if present
    t = re.sub(r"^\s*```json\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^\s*```\s*", "", t)

    # Remove ending fence
    t = re.sub(r"\s*```\s*$", "", t)

    return t.strip()


def translate_hi_to_en(hindi_text: str) -> str:
    """
    Uses local Ollama model to translate Hindi -> English.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": _TRANSLATION_SYSTEM_PROMPT},
            {"role": "user", "content": hindi_text},
        ],
        "stream": False,
        "options": {"temperature": 0.0},
    }

    r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180)
    r.raise_for_status()

    raw = r.json()["message"]["content"]
    return _cleanup_translation(raw)


def normalize_contract_text(text: str, detected_lang: str) -> NormalizationResult:
    """
    If detected language is Hindi, translate to English.
    Otherwise return input as-is.
    """
    lang = (detected_lang or "unknown").lower().strip()

    if lang == "hi":
        en_text = translate_hi_to_en(text)
        return NormalizationResult(
            original_language="hi",
            normalized_language="en",
            did_normalize=True,
            normalized_text=en_text,
        )

    # en or unknown → keep as-is, but pipeline still treats it as English
    return NormalizationResult(
        original_language=lang if lang in {"en", "unknown"} else "unknown",
        normalized_language="en",
        did_normalize=False,
        normalized_text=text,
    )
