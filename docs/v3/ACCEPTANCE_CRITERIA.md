# V3 MVP acceptance criteria

Status: proposed (Phase 0). These criteria decide whether each phase is done. Quality
targets marked *provisional* are a starting proposal; they may only be changed after
the first measured run, with the measured value and the reason recorded here, and with
owner approval. A target is never lowered silently to make a phase pass.

All metrics are computed by a script over [eval/golden_v0.jsonl](eval/golden_v0.jsonl)
on PostgreSQL (CI's PostGIS service or local Docker), and stored in `rag_eval_runs`
with the commit SHA. Definitions are in [eval/README.md](eval/README.md#metrics).

## Non-regression (every phase, hard gate)

| ID | Criterion | How it is checked |
|---|---|---|
| NR-1 | All existing backend, frontend and mobile CI jobs pass | GitHub Actions on `v3-rag` |
| NR-2 | No existing test is modified or deleted to make V3 pass | Diff review of `backend/tests/`, `frontend/src/*.test.js` |
| NR-3 | `/v1/routes` output is unchanged except the new optional `plan_id` field | Test: same request through the fake OSRM/TomTom fixtures, response equal after removing `plan_id` |
| NR-4 | No changes under `backend/routing/`, `backend/forecasting/`, `backend/traffic/state_engine.py`, except one optional `plan_id` field on `RouteResponseV2` in `routing/schemas.py` | `git diff v2-build...v3-rag -- backend/routing backend/forecasting backend/traffic/state_engine.py` shows only that line |
| NR-5 | `alembic upgrade head` and `alembic check` pass on PostGIS; downgrade of 0004 succeeds | CI migration step + round-trip test |
| NR-6 | Backend Docker image still serves `/health` without external services | Existing CI docker job |

## Phase 1: corpus and lexical retrieval

| ID | Criterion | Target |
|---|---|---|
| P1-1 | Ingest indexes exactly the allowlist in [RETRIEVAL_FTS.md](RETRIEVAL_FTS.md#1-corpus-allowlist-v0) | Test compares indexed `source_ref` set to the allowlist |
| P1-2 | No chunk from `docs/v3/`, untracked files, or files matching secret patterns | Test with planted files |
| P1-3 | Re-running ingest on an unchanged commit writes 0 rows | Test |
| P1-4 | Every chunk has `heading_path`, `commit_sha`, `content_hash`; tables are never split mid-row | Test over the real corpus |
| P1-5 | Retrieval recall@5 on answerable questions (`expected_behavior = answer`) | ≥ 0.80 *provisional* |
| P1-6 | Mean reciprocal rank on the same questions | ≥ 0.60 *provisional* |
| P1-7 | Out-of-scope questions: no chunk above `RAG_MIN_SCORE` | ≥ 0.90 of `out_of_scope` items *provisional*. **Failed on 2026-11-03 and superseded** by the scope check (S-1 to S-9 below; owner decision 2026-11-03) |
| P1-8 | Retrieval latency, p95 over the evaluation set, local PostGIS, warm | ≤ 150 ms *provisional* |
| P1-9 | Full ingest time for the v0 corpus | ≤ 60 s |

## Phase 2: scope check

Design: [SCOPE_CHECK.md](SCOPE_CHECK.md). Cases: [eval/scope_cases_v0.jsonl](eval/scope_cases_v0.jsonl)
(60 cases) and the golden set. All are unit tests (SQLite, no database needed for the check itself).

| ID | Criterion | Target |
|---|---|---|
| S-1 | Negative cases (N-*) are never answered: decision is `out_of_scope` or `scope_unclear`, exactly as each case states | 15 of 15 (hard) |
| S-2 | Golden out-of-scope items OS-01 to OS-04 get `out_of_scope` | 4 of 4 (hard) |
| S-3 | Positive cases (P-*) and golden answerable, explain and facts items: none gets `out_of_scope` | 0 (hard) |
| S-4 | Same sets: share that gets `scope_unclear` instead of `in_scope` | ≤ 5 % *provisional* (P-20 is the one expected today) |
| S-5 | Ambiguous cases (A-*) match their stated decision | 10 of 10 (hard) |
| S-6 | Adversarial cases (X-*) match their stated decision; those with `expected_refusal` are refused by the safety rule before scope, with that code | 15 of 15 (hard) |
| S-7 | Every vocabulary concept: each listed form matches; a substring decoy (e.g. `trafficking`, `beta`) does not | 100 % (hard) |
| S-8 | Out-of-scope and unclear responses use the fixed templates, contain no user text, no citations, and trigger no retrieval call | Test (hard) |
| S-9 | Scope decision is deterministic: the same input gives the same decision 100 times; the check does not touch the database | Test (hard) |

A vocabulary change in Phase 2 or later must keep S-1 to S-9 passing, add a case for the
change, and be recorded with its reason in SCOPE_CHECK.md. `scope_cases_v0` is not edited
to fit a vocabulary change; new expectations go into a new version.

## Phase 2: ask endpoint (no LLM)

| ID | Criterion | Target |
|---|---|---|
| P2-1 | Unauthenticated calls return 401, also with `API_AUTH_REQUIRED=false` | Test (hard) |
| P2-2 | Grounding violations: numbers in answers not found in facts or cited chunks | 0 across the evaluation set (hard) |
| P2-3 | Citation validity: every citation id was retrieved for the request and resolves via `/v1/assistant/sources/{id}` | 100 % (hard) |
| P2-4 | Refusal correctness: `expected_behavior = refuse` items return the expected `refusal_code` | 100 % (hard) |
| P2-5 | False refusals on answerable items (any refusal code, including `scope_unclear`) | ≤ 10 % *provisional* |
| P2-6 | Dated facts: answers quoting a chunk with `measured_on` include that date | 100 % (hard) |
| P2-7 | Rate limit returns 429 after the configured count | Test |
| P2-8 | Retention: rows older than `RAG_QUERY_RETENTION_DAYS` deleted by `run_retention`; `0` stores no question text | Test (hard) |
| P2-9 | `rag_queries` has no user id column | Schema test (hard) |
| P2-10 | Ask latency p95, warm, local, no LLM | ≤ 300 ms *provisional* |
| P2-11 | Backend RSS increase after ingest + 100 asks, in the Docker image | ≤ 50 MB *provisional*, measured with `docker stats` |

## Phase 3: explain route

| ID | Criterion | Target |
|---|---|---|
| P3-1 | Every number in an explanation exists in the cached `RouteResponseV2` (after documented unit conversion: m→km, s→min, one decimal) | Property test over generated plans (hard) |
| P3-2 | The explanation names the same recommended route, reference route, classification and comparison basis as the plan | Test (hard) |
| P3-3 | Free-flow plans repeat the free-flow warning; motorcycle plans repeat the car-graph note | Test (hard) |
| P3-4 | Another user's `plan_id` returns 404; an expired one returns 410 | Test (hard) |
| P3-5 | Cache bounded: oldest entries evicted beyond `RAG_PLAN_CACHE_MAX` | Test |
| P3-6 | Explain-route cases in the evaluation set pass (behaviour per item) | 100 % (hard) |

## Phase 5a: minimal web UI

| ID | Criterion | Target |
|---|---|---|
| P5-1 | "Why this route?" on each route card calls explain-route with the plan's `plan_id` | Jest test |
| P5-2 | Ask panel shows answer, citation chips, `as_of` for facts, and refusal reasons | Jest test |
| P5-3 | Answers rendered as text (no `dangerouslySetInnerHTML`) | Code check + test with an HTML payload |
| P5-4 | 410 triggers one automatic re-plan and retry | Jest test |
| P5-5 | `npm run build` passes; manual walkthrough on a local plan recorded in TEST_REPORT.md | Build + note |

## MVP definition of done

* All hard criteria above pass; provisional targets are met or have an approved,
  recorded revision.
* `docs/v3/` updated with measured results, labelled with date and commit.
* No new runtime dependency in `backend/requirements.txt` for the MVP.
* The owner approves the merge plan (`v3-rag` stays separate from `v2-build` until then).

## Phase 6 embeddings gate

Hybrid retrieval replaces lexical as default only if all hold, measured on the same
evaluation set version:

* recall@5 improves by ≥ 0.05 absolute, and MRR does not decrease;
* P2-2, P2-3, P2-4 still pass;
* backend RSS stays ≤ 450 MB in a `-m 512m` container after warm-up and 100 asks;
* cold first-ask latency (model load) ≤ 10 s, warm p95 ≤ 400 ms.

Otherwise lexical stays the default and the result is recorded as a negative result.
