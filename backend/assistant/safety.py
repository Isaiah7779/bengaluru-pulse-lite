"""Safety rules that run before the scope check (docs/v3/RAG_SAFETY.md, SCOPE_CHECK.md §1).

Deterministic patterns, no model. A question that matches is refused with a fixed
template; it is never retrieved, so nothing about secrets, other users or invented
numbers can reach an answer. The rules are deliberately broad: a false refusal costs a
rephrase, a missed one could leak data or invite a fabricated answer.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

MAX_QUESTION_CHARS = 500

_CONTROL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‍⁠﻿]")


def clean_question(text: str) -> str:
    """NFKC, control and zero-width characters removed, whitespace collapsed."""

    text = _CONTROL.sub("", unicodedata.normalize("NFKC", text))
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class SafetyRefusal:
    code: str  # refusal_code returned to the client
    reason: str  # which rule fired (logged, also returned)
    message: str


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


# Instruction override / prompt injection.
_OVERRIDE = _rx(
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,30}\b(rules?|instructions?|prompt|guidelines|polic(y|ies)|restrictions?)\b",
    r"^\s*(system|developer|assistant)\s*:",
    r"\byou are now\b", r"\b(developer|admin|god|debug|jailbreak)\s+mode\b", r"\bjailbreak\b",
    r"\bpretend (you are|to be)\b", r"\bact as (an?|the)\b", r"\b(system|hidden) prompt\b",
    r"\breveal your\b",
)

# Credentials, keys and configuration.
_CREDENTIALS = _rx(
    r"\bapi[\s_-]?keys?\b", r"\b(secret|secrets)\b", r"\b(access|auth|bearer|jwt|id)[\s_-]?tokens?\b",
    r"\bcredentials?\b", r"\.env\b", r"\benv(ironment)? (vars?|variables?)\b", r"\bprivate key\b",
    r"\bdatabase[\s_-]?url\b", r"\bconnection string\b", r"\bjwt[\s_-]?secret\b",
    r"\b(server|backend|app) config(uration)?\b", r"\bpasswords? (of|for) (the |another |other )?(admin|user|users|account|database)\b",
    r"\b(hack|exploit|bypass)\b.{0,30}\b(quota|limit|auth|login|api)\b",
)

# Other people's data and unmoderated content.
_PERSONAL = _rx(
    r"\b(another|other|some(one)?|any|which|who)\b.{0,20}\b(users?|people|person|reporters?)\b.{0,40}\b(trips?|history|data|emails?|account|submitted|reported|location|favourites)\b",
    r"\b(users?|reporters?|members?)'?s?\b.{0,15}\b(emails?|phone|names?|addresses|locations?|trip history)\b",
    r"\bwho (submitted|reported|uploaded|shared)\b",
    r"\bpending (incident|report|submission)s?\b", r"\blist (all )?(users|accounts|emails)\b",
)

# Requests to invent or guess numbers.
_FABRICATION = _rx(
    r"\bmake (up|something up)\b", r"\b(just )?guess\b", r"\binvent\b", r"\bmade[- ]up\b",
    r"\bassume (there|that|a|an)\b", r"\bhypothetical(ly)?\b", r"\bestimate (it )?yourself\b",
    r"\broughly is fine\b", r"\bmake (a|some) numbers?\b",
)

# Requests for a prediction Pulse cannot serve (no evaluated model is active).
_PREDICTION = _rx(
    r"^\s*predict\b", r"\bpredict (the |how |what |tomorrow|traffic|congestion)",
    r"\bwhat will (the )?(traffic|congestion|roads?)\b", r"\bhow (bad|busy|heavy) will\b",
    r"\bwill (the )?(traffic|congestion|jam|roads?)\b.{0,40}\b(tomorrow|tonight|next|later|this (evening|weekend)|at \d)",
    r"\busually how long\b", r"\btypically take\b",
)

_TEMPLATES = {
    "instruction_override": "I can't change how I work or ignore my rules. Ask me about routes, traffic or how Bengaluru Pulse works.",
    "credential_request": "I can't share keys, passwords, tokens or server configuration.",
    "personal_data": "I can't share information about other users, their trips or unpublished reports.",
    "fabrication_request": (
        "I don't guess or invent travel times, incidents or routes. Use Find routes on the Navigate "
        "page to get measured or provider-predicted times."
    ),
    "prediction_unavailable": (
        "Pulse has no validated forecasting model yet, so I can't predict traffic. To see TomTom's "
        "predicted travel time, plan a route with a future departure on the Navigate page."
    ),
    "too_long": f"Please keep your question under {MAX_QUESTION_CHARS} characters.",
    "empty": "Please type a question.",
}

# refusal_code per reason (the codes in RAG_SAFETY.md §2; override and credential
# requests are refused as out of scope, matching golden items PI-01 / PI-02).
_CODES = {
    "instruction_override": "out_of_scope",
    "credential_request": "out_of_scope",
    "personal_data": "personal_data",
    "fabrication_request": "fabrication_request",
    "prediction_unavailable": "prediction_unavailable",
    "too_long": "invalid_question",
    "empty": "invalid_question",
}


def refusal(reason: str) -> SafetyRefusal:
    return SafetyRefusal(_CODES[reason], reason, _TEMPLATES[reason])


def check(question: str) -> Optional[SafetyRefusal]:
    """Return a refusal if a safety rule applies, else None. Order matters: most severe first."""

    if not question:
        return refusal("empty")
    if len(question) > MAX_QUESTION_CHARS:
        return refusal("too_long")
    if _PERSONAL.search(question):
        return refusal("personal_data")
    if _CREDENTIALS.search(question):
        return refusal("credential_request")
    if _OVERRIDE.search(question):
        return refusal("instruction_override")
    if _FABRICATION.search(question):
        return refusal("fabrication_request")
    if _PREDICTION.search(question):
        return refusal("prediction_unavailable")
    return None


# --------------------------------------------------------------------------- retrieved text

_HTML_TAG = re.compile(r"<[^>]{0,200}>")
_MD_LINK = re.compile(r"\[([^\]]{0,200})\]\([^)]{0,500}\)")


def sanitize_passage(text: str) -> str:
    """Retrieved text is untrusted data: plain text only (no tags, links reduced to their label)."""

    text = _MD_LINK.sub(r"\1", _HTML_TAG.sub("", text))
    return _CONTROL.sub("", text).strip()
