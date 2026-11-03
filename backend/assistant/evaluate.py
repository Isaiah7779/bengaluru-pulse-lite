"""Retrieval metrics over the evaluation set (docs/v3/ACCEPTANCE_CRITERIA.md, Phase 1).

    python -m assistant.evaluate              # uses DATABASE_URL; ingest first
    python -m assistant.evaluate --record     # also stores the run in rag_eval_runs

Metrics count on PostgreSQL only; on SQLite the run is labelled and not a result.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from assistant import golden
from assistant.corpus import resolve_commit
from assistant.retrieval import get_retriever
from db.models import RagEvalRun

K = 5
MRR_DEPTH = 10


def _percentile(values: List[float], pct: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[idx]


def run(session: Session, items: Optional[List[Dict]] = None) -> Dict:
    items = golden.scored(items if items is not None else golden.load())
    retriever = get_retriever(session)
    answerable = [i for i in items if i["expected_behavior"] == "answer"]
    out_of_scope = [i for i in items if i["category"] == "out_of_scope"]

    retriever.search("warm up the connection", k=K)
    per_item, latencies = [], []
    for item in answerable:
        started = time.perf_counter()
        hits = retriever.search(item["question"], k=MRR_DEPTH)
        latencies.append((time.perf_counter() - started) * 1000)
        rank = next((n for n, h in enumerate(hits, 1)
                     if any(golden.matches(s, h.source_ref, h.heading_path) for s in item["expected_sources"])), None)
        per_item.append({"id": item["id"], "rank": rank, "top": [f"{h.source_ref} :: {h.heading_path}" for h in hits[:3]],
                         "top_score": hits[0].score if hits else None})

    oos = []
    for item in out_of_scope:
        hits = retriever.search(item["question"], k=1)
        oos.append({"id": item["id"], "top_score": hits[0].score if hits else None,
                    "top": f"{hits[0].source_ref} :: {hits[0].heading_path}" if hits else None})

    recall = sum(1 for p in per_item if p["rank"] and p["rank"] <= K) / len(per_item)
    mrr = sum(1 / p["rank"] for p in per_item if p["rank"]) / len(per_item)
    answer_scores = [p["top_score"] for p in per_item if p["top_score"] is not None]
    return {
        "retriever": retriever.name,
        "counts_as_result": retriever.name == "postgres_fts",
        "answerable_items": len(per_item),
        "recall_at_5": round(recall, 4),
        "mrr_at_10": round(mrr, 4),
        "latency_ms_p50": round(statistics.median(latencies), 2),
        "latency_ms_p95": round(_percentile(latencies, 95), 2),
        "answerable_top_score_min": round(min(answer_scores), 4) if answer_scores else None,
        "answerable_top_score_median": round(statistics.median(answer_scores), 4) if answer_scores else None,
        "out_of_scope": oos,
        "misses": [p for p in per_item if not p["rank"] or p["rank"] > K],
    }


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate assistant retrieval")
    parser.add_argument("--record", action="store_true", help="store the run in rag_eval_runs")
    args = parser.parse_args(argv)
    from db.session import session_scope

    with session_scope() as s:
        metrics = run(s)
        if args.record:
            s.add(RagEvalRun(golden_set=golden.GOLDEN_PATH.name, retriever=metrics["retriever"],
                             commit_sha=resolve_commit("HEAD"), metrics=metrics))
    print(json.dumps(metrics, indent=2, default=str))


if __name__ == "__main__":
    main()
