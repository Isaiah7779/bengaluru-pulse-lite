"""Text normalisation shared by the gazetteer build and search (no heavy deps)."""

from __future__ import annotations

import re
import unicodedata

_ABBREVIATIONS = {
    "rd": "road", "st": "street", "jn": "junction", "jct": "junction", "ngr": "nagar",
    "blr": "bengaluru", "bangalore": "bengaluru", "bengalooru": "bengaluru", "mg": "mg",
    "opp": "opposite", "nr": "near", "stn": "station", "hosp": "hospital", "univ": "university",
    "apt": "apartment", "apts": "apartments", "layout": "layout", "lyt": "layout", "extn": "extension",
    "x": "cross", "crs": "cross", "mn": "main",
}


def normalize(text: str) -> str:
    """Lower-case, strip accents/punctuation and expand common abbreviations."""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    tokens = [_ABBREVIATIONS.get(t, t) for t in text.split()]
    return " ".join(tokens)
