"""Expansion-role classification + expansion-type inference.

The judgment: a single remote sales hire in a city is NOT an expansion. A *cluster* of
on-site roles — especially facilities/site-lead/ops/engineering-hub roles — is. We score
each job title and let the corroborator weight by how many expansion-indicating roles
land in the same new metro.
"""

from __future__ import annotations

import re

from signal_connector.models import ExpansionType

# Titles that indicate standing up a physical/hub presence (not a hire-from-anywhere role).
EXPANSION_ROLE_PATTERNS = re.compile(
    r"\b(site lead|general manager|office manager|facilities|site reliability|"
    r"head of|director|principal|staff|construction|electrician|technician|"
    r"production|assembly|warehouse|operations|infrastructure|data ?cent(er|re)|"
    r"research|machine learning|ml scientist|platform engineer)\b",
    re.I,
)

# Type inference from role/title vocabulary present in the metro's job cluster.
_TYPE_HINTS: list[tuple[ExpansionType, re.Pattern]] = [
    (ExpansionType.DATACENTER,
     re.compile(r"data ?cent(er|re)|colossus|energy storage|electrical", re.I)),
    (ExpansionType.MANUFACTURING,
     re.compile(r"manufactur|assembly|production|fabrication|factory", re.I)),
    (ExpansionType.WAREHOUSE, re.compile(r"warehouse|fulfillment|distribution", re.I)),
    (ExpansionType.RETAIL, re.compile(r"retail|store|showroom", re.I)),
    (ExpansionType.RD,
     re.compile(r"research|machine learning|ml |ai |engineer|scientist|r&d", re.I)),
]


def is_expansion_role(title: str) -> bool:
    return bool(EXPANSION_ROLE_PATTERNS.search(title or ""))


def infer_expansion_type(titles: list[str]) -> ExpansionType:
    """Pick the dominant expansion type from a cluster of job titles. Defaults to office."""
    scores: dict[ExpansionType, int] = {}
    blob = " ".join(titles)
    for etype, pat in _TYPE_HINTS:
        hits = len(pat.findall(blob))
        if hits:
            scores[etype] = hits
    if not scores:
        return ExpansionType.OFFICE
    return max(scores, key=lambda k: scores[k])
