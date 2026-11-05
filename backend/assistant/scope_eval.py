"""Score the scope check on a labelled file (docs/v3/SCOPE_CHECK.md §8–§9).

    python -m assistant.scope_eval ../docs/v3/eval/heldout_scope_v1.jsonl

Each line needs `id`, `question` and `expected` (`in_scope` | `out_of_scope` | `ambiguous`)
or `expected_scope` (`in_scope` | `out_of_scope` | `scope_unclear`). `ambiguous` is
scored as `scope_unclear`, the conservative fallback. Prints a confusion matrix and rates.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

from assistant import scope

LABELS = (scope.IN_SCOPE, scope.OUT_OF_SCOPE, scope.SCOPE_UNCLEAR)


def expected_of(item: Dict) -> str:
    value = item.get("expected_scope") or item["expected"]
    return scope.SCOPE_UNCLEAR if value == "ambiguous" else value


def evaluate(items: List[Dict]) -> Dict:
    rows = []
    matrix: Counter = Counter()
    for item in items:
        got = scope.classify(item["question"]).decision
        want = expected_of(item)
        matrix[(want, got)] += 1
        rows.append({"id": item["id"], "expected": want, "got": got})

    def count(want=None, got=None):
        return sum(v for (w, g), v in matrix.items() if (want is None or w == want) and (got is None or g == got))

    not_in = count(want=scope.OUT_OF_SCOPE) + count(want=scope.SCOPE_UNCLEAR)
    in_total = count(want=scope.IN_SCOPE)
    unclear_total = count(want=scope.SCOPE_UNCLEAR)
    return {
        "items": len(items),
        "accuracy": round(sum(1 for r in rows if r["expected"] == r["got"]) / len(rows), 4),
        "confusion_matrix": {w: {g: matrix[(w, g)] for g in LABELS} for w in LABELS},
        # answered although it should not be (out of scope or ambiguous predicted in_scope)
        "false_positive_rate": round((count(scope.OUT_OF_SCOPE, scope.IN_SCOPE) + count(scope.SCOPE_UNCLEAR, scope.IN_SCOPE)) / not_in, 4) if not_in else None,
        # an in-scope question not answered (refused or sent to fallback)
        "false_negative_rate": round((in_total - count(scope.IN_SCOPE, scope.IN_SCOPE)) / in_total, 4) if in_total else None,
        "in_scope_refused_out_of_scope": count(scope.IN_SCOPE, scope.OUT_OF_SCOPE),
        "in_scope_sent_to_fallback": count(scope.IN_SCOPE, scope.SCOPE_UNCLEAR),
        "ambiguous_fallback_rate": round(count(scope.SCOPE_UNCLEAR, scope.SCOPE_UNCLEAR) / unclear_total, 4) if unclear_total else None,
        "mismatches": [r for r in rows if r["expected"] != r["got"]],
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate the scope check on a labelled JSONL file")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    items = [json.loads(l) for l in args.path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(json.dumps(evaluate(items), indent=2))


if __name__ == "__main__":
    main()
