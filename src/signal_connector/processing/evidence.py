"""Extract 'what's happening' details from corroborating text → richer evidence payload.
Turns 'Intercom → Berlin' into 'Intercom → Berlin R&D, 100 hires, $X, by July 2026'.
Deterministic regex extraction (no LLM in the hot path)."""

from __future__ import annotations

import re

_HEADCOUNT = re.compile(
    r"\b(\d{2,5})\s*(?:\+|new)?\s*(?:hires|jobs|roles|employees|staff|people|workers|positions)\b",
    re.I,
)
_SCALE_TO = re.compile(r"\b(?:scal\w+|grow\w+|expand\w+)\s+to\s+(\d{2,5})\b", re.I)
_INVESTMENT = re.compile(r"\$\s?\d[\d,.]*\s*(?:billion|million|bn|m\b|b\b)?", re.I)
_TIMELINE = re.compile(
    r"\b(?:by\s+|in\s+|targets?\s+|begin\w*\s+\w+\s+)?"
    r"(?:Q[1-4]\s*20\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+20\d{2}|20\d{2})\b",
    re.I,
)


def extract_evidence(texts: list[str]) -> dict:
    """Pull headcountTarget / investment / timeline from a list of snippets/titles."""
    blob = " ".join(t for t in texts if t)
    out: dict = {}

    counts = [int(m) for m in _HEADCOUNT.findall(blob)] + [
        int(m) for m in _SCALE_TO.findall(blob)
    ]
    if counts:
        out["headcountTarget"] = max(counts)

    inv = _INVESTMENT.search(blob)
    if inv:
        out["investment"] = inv.group(0).strip()

    tl = _TIMELINE.search(blob)
    if tl:
        out["timeline"] = tl.group(0).strip()

    return out
