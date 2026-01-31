from __future__ import annotations

import re
from typing import Dict, Any, List

import spacy

# Lazy-loaded spaCy pipeline
_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        try:
            _NLP = spacy.load("en_core_web_sm")
        except Exception as e:
            raise RuntimeError(
                "spaCy model 'en_core_web_sm' not found. Run: python -m spacy download en_core_web_sm"
            ) from e
    return _NLP


MONEY_PATTERNS = [
    re.compile(r"(₹\s?[\d,]+(?:\.\d+)?)", re.I),
    re.compile(r"\bINR\s?[\d,]+(?:\.\d+)?\b", re.I),
    re.compile(r"\bRs\.?\s?[\d,]+(?:\.\d+)?\b", re.I),
]

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4})\b", re.I),
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b((Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4})\b", re.I),
]

JURISDICTION_PATTERNS = [
    re.compile(r"\b(governing law)\b", re.I),
    re.compile(r"\b(governed by the laws of\s+([A-Za-z\s]+))\b", re.I),
    re.compile(r"\b(exclusive jurisdiction)\b", re.I),
    re.compile(r"\b(courts?\s+of\s+([A-Za-z\s]+))\b", re.I),
    re.compile(r"\b(jurisdiction)\b", re.I),
]


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        x = (x or "").strip()
        if not x:
            continue
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def extract_parties(text: str) -> Dict[str, Any]:
    """
    Extracts party roles if the contract defines them like:
      ABC Pvt Ltd ("Client"), XYZ Ltd ("Vendor")
    """
    t = text or ""
    roles: Dict[str, str] = {}

    role_pat = re.compile(
        r"([A-Z][A-Za-z0-9&.,\-\s]{2,120})\s*\(\s*\"?(Client|Vendor|Employer|Employee|Lessor|Lessee|Landlord|Tenant)\"?\s*\)",
        re.I,
    )

    for m in role_pat.finditer(t):
        name = m.group(1).strip()
        role = m.group(2).strip().lower()
        roles[role] = name

    mentions = []
    for term in ["Client", "Vendor", "Employer", "Employee", "Lessor", "Lessee", "Landlord", "Tenant", "Partner"]:
        if re.search(rf"\b{term}\b", t, flags=re.I):
            mentions.append(term)

    return {"roles": roles, "party_mentions": _dedupe(mentions)}


def extract_entities(text: str) -> Dict[str, Any]:
    """
    spaCy + regex hybrid NER over normalized English text.
    Output is JSON-safe.
    """
    nlp = _get_nlp()
    doc = nlp(text or "")

    orgs, persons, locs, dates, money = [], [], [], [], []

    for ent in doc.ents:
        if ent.label_ == "ORG":
            orgs.append(ent.text)
        elif ent.label_ == "PERSON":
            persons.append(ent.text)
        elif ent.label_ in {"GPE", "LOC"}:
            locs.append(ent.text)
        elif ent.label_ == "DATE":
            dates.append(ent.text)
        elif ent.label_ == "MONEY":
            money.append(ent.text)

    # Regex extraction (catches INR/₹ formats not always tagged)
    for pat in MONEY_PATTERNS:
        for m in pat.findall(text or ""):
            if isinstance(m, tuple):
                money.append(m[0])
            else:
                money.append(m)

    for pat in DATE_PATTERNS:
        hits = pat.findall(text or "")
        for h in hits:
            if isinstance(h, tuple):
                dates.append(h[0])
            else:
                dates.append(h)

    juris = []
    for pat in JURISDICTION_PATTERNS:
        for m in pat.finditer(text or ""):
            juris.append(m.group(0))

    parties = extract_parties(text or "")

    return {
        "parties": parties,
        "organizations": _dedupe(orgs),
        "persons": _dedupe(persons),
        "locations": _dedupe(locs),
        "dates": _dedupe(dates),
        "money_amounts": _dedupe(money),
        "jurisdiction_mentions": _dedupe(juris),
    }
