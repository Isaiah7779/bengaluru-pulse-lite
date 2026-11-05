# Phase 1 results: corpus and lexical retrieval

Measured 2026-11-03 on a throwaway database in the local `postgis/postgis:16-3.4`
container (Windows laptop, warm). Corpus read from commit `d2ec291`; evaluation set
`docs/v3/eval/golden_v0.jsonl` (78 items, 53 answerable, 4 out of scope). Reproduce:
`python -m alembic upgrade head && python -m assistant.ingest && python -m assistant.evaluate`
from `backend/` with `DATABASE_URL` pointing at an empty PostGIS database.

## Against the acceptance criteria

| ID | Criterion | Target | Measured | Result |
|---|---|---|---|---|
| NR-1 | Backend suite | all pass | 188 passed, 0 skipped (live OSRM and PostGIS up) | pass (CI not yet run) |
| NR-2 | Existing tests unchanged | none modified | 2 new files only | pass |
| NR-4 | No change to routing / forecasting / state engine | none | none | pass |
| NR-5 | `alembic upgrade head`, `check`, downgrade round trip on PostGIS | clean | clean (existing round-trip test now covers 0004) | pass |
| P1-1 | Ingest indexes exactly the allowlist | equal sets | 12 of 12 | pass (test) |
| P1-2 | No `docs/v3/`, untracked or credential-bearing files | refused | refused | pass (tests with planted files) |
| P1-3 | Re-ingest of an unchanged commit writes 0 rows | 0 | 0 | pass |
| P1-4 | Chunk metadata present; tables never split mid-row | yes | yes | pass (tests) |
| P1-5 | recall@5, answerable items | ≥ 0.80 | **0.830** (44 of 53) | pass |
| P1-6 | MRR@10 | ≥ 0.60 | **0.663** | pass |
| P1-7 | Out-of-scope items with no chunk above `RAG_MIN_SCORE` | ≥ 0.90 | **not achievable with a score floor** (see below) | **fail** |
| P1-8 | Retrieval latency p95, warm | ≤ 150 ms | 11.6–17.5 ms over two runs (p50 ≈ 10.5 ms) | pass |
| P1-9 | Full ingest | ≤ 60 s | 1.2–1.3 s (75 chunks) | pass |

## P1-7: why a score floor cannot reject out-of-scope questions

`ts_rank_cd(..., 32)` scores for the four out-of-scope questions were 0.286–0.667.
The answerable questions' top scores had a median of 0.818 but a minimum of 0.006
(SP-06 scored 0.123, FC-03 0.046). Any floor that rejects all four out-of-scope
questions (> 0.667) would also reject many answerable ones. The normalised rank
mostly reflects how many query words match, not whether the question is about Pulse
("biryani place in **Koramangala**" matches the Koramangala routing benchmarks).

Approved by the owner on 2026-11-03 and specified in [SCOPE_CHECK.md](SCOPE_CHECK.md):
do not use a score floor. Instead decide scope deterministically before retrieval. The
question must contain at least one term from a reviewed domain vocabulary (routing,
traffic, forecast, incident, shortcut, account, and so on). Place names alone do not
count. Anything else gets `out_of_scope`. P1-7 is replaced by criteria S-1 to S-9
in ACCEPTANCE_CRITERIA.md.

## Misses (expected source not in the top 5)

| Item | Question (short) | Rank of expected source |
|---|---|---|
| RT-11 | Does weather change the ETA? | not in top 10 |
| TR-01 | Where does live traffic data come from? | 7 |
| TR-07 | Can I download the collected data? | not in top 10 |
| FC-01 | Is the Pulse forecast turned on? | not in top 10 |
| FC-03 | What must a model do before routing uses it? | not in top 10 |
| CM-02 | Why can't others see my incident report? | 7 |
| CM-03 | Are verified shortcuts used as route options? | not in top 10 |
| SP-03 | How many incident reports per hour? | not in top 10 |
| SP-06 | Do I need an account to plan a route? | 6 |

The query-expansion table was **not** tuned to these misses: changing it to fix
specific evaluation items would overfit the test set. Paraphrase gaps of this kind
are what Phase 6 (embeddings) is meant to address and will be measured against.

## Notes

* Chunk overlap: a short last paragraph (≤ 50 words) is carried into the next window.
  Tables and code are never carried or cut, so overlap is by whole paragraph, not a
  fixed 50-word slice. RETRIEVAL_FTS.md §2 is updated to say so.
* The SQLite BM25 retriever is exercised by unit tests only; no metric above comes
  from it.
* The ingest CLI reads files with `git show <commit>:<path>`, so it needs a git
  checkout. It does not run inside the backend Docker image (no git, no `docs/`).
