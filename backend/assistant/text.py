"""Text normalisation and tokenisation shared by ingest, retrieval and evaluation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import List

# NFKC leaves U+2010/U+2011 (the docs use non-breaking hyphens in dates) as non-ASCII.
_HYPHENS = str.maketrans({"‐": "-", "‑": "-"})
_TOKEN = re.compile(r"[a-z0-9_]+")

# Small English stopword list for the SQLite BM25 path; PostgreSQL uses its own
# 'english' configuration.
STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in into is it its "
    "me my of on or so than that the their then there these this to was what when where which "
    "who why will with you your".split()
)


def normalise(text: str) -> str:
    """NFKC, ASCII hyphens, collapsed whitespace. Case is kept for display."""

    text = unicodedata.normalize("NFKC", text).translate(_HYPHENS)
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    """Normalised, lower-cased form used for matching."""

    return normalise(text).lower()


def tokens(text: str) -> List[str]:
    return _TOKEN.findall(fold(text))


def content_tokens(text: str) -> List[str]:
    return [t for t in tokens(text) if t not in STOPWORDS]


def sha256(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    return len(text.split())
