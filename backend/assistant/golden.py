"""Load the evaluation set and match retrieved chunks to expected sources (docs/v3/eval/README.md)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from assistant.chunking import HEADING_SEP
from assistant.corpus import REPO_ROOT
from assistant.text import fold

GOLDEN_PATH = REPO_ROOT / "docs" / "v3" / "eval" / "golden_v0.jsonl"


def load(path: Path = GOLDEN_PATH) -> List[Dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def scored(items: List[Dict]) -> List[Dict]:
    return [i for i in items if not i.get("status")]


def matches(source: Dict, source_ref: str, heading_path: str) -> bool:
    """Same file, and some heading on the chunk's path starts with the expected prefix."""

    if source["path"] != source_ref:
        return False
    prefix = fold(source.get("heading_prefix", ""))
    if not prefix:
        return True
    return any(fold(h).startswith(prefix) for h in heading_path.split(HEADING_SEP)[1:])
