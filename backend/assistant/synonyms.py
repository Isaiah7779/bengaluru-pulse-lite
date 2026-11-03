"""Reviewed query-expansion table (docs/v3/RETRIEVAL_FTS.md §4).

Rewrites replace a term in the query; expansions add OR-terms to the loose query.
PostgreSQL thesaurus dictionaries need files on the database server, which managed
Postgres does not allow, so expansion happens here. Keep entries few and obvious.
"""

from __future__ import annotations

import re
from typing import List, Tuple

# Applied to the folded question before tokenising (phrase -> replacement).
REWRITES: Tuple[Tuple[str, str], ...] = (
    (r"\bshort cuts?\b", "shortcut"),
    (r"\blong cuts?\b", "longcut"),
    (r"\bkia\b", "airport"),
    (r"\borr\b", "outer ring road"),
    (r"\bu\b", "you"),
    (r"\bpwd\b", "password"),
)

# Token -> extra OR-terms for the loose query.
EXPANSIONS = {
    "eta": ["travel", "time", "duration"],
    "jam": ["congestion", "delay"],
    "traffic": ["congestion"],
    "quicker": ["faster"],
    "slower": ["delay"],
    "accident": ["incident"],
    "crash": ["incident"],
    "closure": ["incident"],
    "bike": ["bicycle", "motorcycle"],
    "two": ["motorcycle"],
    "wheeler": ["motorcycle"],
    "predict": ["forecast"],
    "prediction": ["forecast"],
    "accurate": ["accuracy", "mae", "evaluation"],
    "accuracy": ["mae", "evaluation"],
    "login": ["sign"],
    "signin": ["sign"],
    "account": ["sign"],
    "delete": ["deletion", "retention"],
    "keep": ["retention"],
    "kept": ["retention"],
    "reset": ["password"],
    "toll": ["avoid"],
    "tolls": ["avoid"],
    "hosted": ["free", "tier", "render"],
    "slow": ["cold", "start", "sleeps"],
    "duplicate": ["dedup", "similarity"],
    "duplicates": ["dedup", "similarity"],
    "label": ["classification"],
    "weather": ["open", "meteo"],
}


def rewrite(folded: str) -> str:
    for pattern, replacement in REWRITES:
        folded = re.sub(pattern, replacement, folded)
    return folded


def expand(tokens: List[str]) -> List[str]:
    extra: List[str] = []
    for t in tokens:
        for e in EXPANSIONS.get(t, ()):
            if e not in tokens and e not in extra:
                extra.append(e)
    return extra
