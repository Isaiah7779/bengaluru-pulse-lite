"""Deterministic scope check (docs/v3/SCOPE_CHECK.md).

Decides `in_scope`, `out_of_scope` or `scope_unclear` from a reviewed vocabulary.
No database, no model, no score. Place names never make a question in scope, and
whatever the rules cannot settle confidently falls back to `scope_unclear`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Tuple

from assistant import scope_terms as terms

IN_SCOPE = "in_scope"
OUT_OF_SCOPE = "out_of_scope"
SCOPE_UNCLEAR = "scope_unclear"

NON_LATIN_SHARE = 0.3
MIN_TOKENS = 2

TEMPLATES: Dict[str, str] = {
    OUT_OF_SCOPE: (
        "I can only help with Bengaluru Pulse: routes, traffic, incidents, weather for your trip, "
        "forecasts and how the app works. I can't help with this question."
    ),
    SCOPE_UNCLEAR: (
        "I'm not sure this question is about routes or traffic. Could you rephrase it? For example: "
        "\"Why is this route recommended?\", \"Is there an incident near Silk Board?\" or "
        "\"How are shortcuts verified?\""
    ),
    "non_latin": (
        "I can only read questions in English for now. Could you ask in English? For example: "
        "\"How is traffic on Outer Ring Road?\""
    ),
}

_HYPHENS = str.maketrans({"‐": "-", "‑": "-"})
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
_APOSTROPHES = re.compile("['’]")
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ScopeDecision:
    decision: str
    rule: str  # which rule of SCOPE_CHECK.md §4 decided
    strong: FrozenSet[str] = field(default_factory=frozenset)
    weak: FrozenSet[str] = field(default_factory=frozenset)
    negative: FrozenSet[str] = field(default_factory=frozenset)
    places: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def message(self) -> str:
        if self.decision == IN_SCOPE:
            return ""
        return TEMPLATES["non_latin" if self.rule == "7-script" else self.decision]


def tokenise(question: str) -> List[str]:
    text = unicodedata.normalize("NFKC", question).translate(_HYPHENS).lower()
    text = _APOSTROPHES.sub("", _ZERO_WIDTH.sub("", text))
    return _TOKEN.findall(text)


def _plural_forms(form: str) -> Tuple[str, ...]:
    """Single-word negative forms also accept a plural ("restaurants", "dentists")."""

    if " " in form:
        return (form,)
    return (form, form + "s", form + "es")


def _build_patterns() -> List[Tuple[int, str, str, Tuple[str, ...]]]:
    """(length, tier, concept, tokens), longest first so phrases win over their words."""

    patterns = [(len(p.split()), "place", p, tuple(p.split())) for p in terms.PLACES]
    patterns += [(len(c.split()), "cue", c, tuple(c.split())) for c in terms.TRAVEL_CUES]
    for tier, table in (("strong", terms.STRONG), ("negative", terms.NEGATIVE), ("weak", terms.WEAK)):
        for concept, forms in table.items():
            for form in forms:
                for f in (_plural_forms(form) if tier == "negative" else (form,)):
                    patterns.append((len(f.split()), tier, concept, tuple(f.split())))
    order = {"place": 0, "strong": 1, "negative": 2, "weak": 3, "cue": 4}
    return sorted(set(patterns), key=lambda p: (-p[0], order[p[1]], p[2], p[3]))


_PATTERNS = _build_patterns()


def _non_latin_share(question: str) -> float:
    letters = [c for c in question if c.isalpha()]
    return sum(1 for c in letters if not c.isascii()) / len(letters) if letters else 0.0


def classify(question: str, has_plan: bool = False) -> ScopeDecision:
    if _non_latin_share(question) > NON_LATIN_SHARE:
        return ScopeDecision(SCOPE_UNCLEAR, "7-script")

    tokens = tokenise(question)
    used = [False] * len(tokens)
    found: Dict[str, set] = {"strong": set(), "weak": set(), "negative": set(), "place": set(), "cue": set()}
    demoted: set = set()
    place_tokens = 0
    for length, tier, concept, pattern in _PATTERNS:
        for i in range(len(tokens) - length + 1):
            if tuple(tokens[i:i + length]) != pattern or any(used[i:i + length]):
                continue
            for j in range(i, i + length):
                used[j] = True
            if tier == "place":
                place_tokens += length
                found["place"].add(concept)
            elif tier == "strong" and any(t in terms.NEGATORS for t in tokens[max(0, i - terms.NEGATION_WINDOW):i]):
                found["weak"].add(concept)  # negation demotes, it does not remove (§5)
                demoted.add(concept)
            else:
                found[tier].add(concept)

    def decide(decision: str, rule: str) -> ScopeDecision:
        return ScopeDecision(decision, rule, frozenset(found["strong"]), frozenset(found["weak"]),
                             frozenset(found["negative"]), frozenset(found["place"]))

    if len(tokens) - place_tokens < MIN_TOKENS:
        return decide(SCOPE_UNCLEAR, "7-short")
    s = len(found["strong"]) + (1 if has_plan else 0)
    w, n = len(found["weak"]), len(found["negative"])
    if s >= 1:
        return decide(IN_SCOPE, "1") if n == 0 else decide(SCOPE_UNCLEAR, "2")
    if n >= 1:
        return decide(OUT_OF_SCOPE, "5")
    # A demoted (negated) strong concept still names a traffic subject, so it counts as an anchor.
    anchors = len(found["weak"] & terms.WEAK_ANCHOR) + len(demoted)
    app = len(found["weak"] & terms.WEAK_APP)
    if w >= 2 and (anchors >= 1 or app >= 2):
        return decide(IN_SCOPE, "3")
    if w >= 1:
        return decide(SCOPE_UNCLEAR, "4")
    if found["place"] or found["cue"]:
        return decide(SCOPE_UNCLEAR, "6-travel")
    return decide(OUT_OF_SCOPE, "6")
