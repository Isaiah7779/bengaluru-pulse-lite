# ADR-0001: Retrieval-augmented assistant for Bengaluru Pulse (V3 MVP)

| Field | Value |
|---|---|
| Status | Proposed (Phase 0, awaiting owner review) |
| Date | 2026-11-03 |
| Baseline | `v2-build` at `fac06c3` (CI green); work happens on `v3-rag` |
| Related | [RAG_SAFETY.md](RAG_SAFETY.md), [RETRIEVAL_FTS.md](RETRIEVAL_FTS.md), [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md), [eval/README.md](eval/README.md) |

## Context

Bengaluru Pulse V2 already produces structured, explainable answers:
`POST /v1/routes` returns `RouteResponseV2` with ranked options, a reference route,
shortcut/longcut classifications, score components, incidents, monitored segments,
weather, data-source status and warnings. Traffic, weather and incident data are
collected into PostgreSQL with timestamps and staleness rules. Forecasts are served
only from an `active` model that passed the evaluation gate (none has, as of the
latest committed reports).

What V2 lacks is a way for a user to ask *why* in their own words ("why is the
longer road recommended?") or to ask how the system works and how reliable it is
without reading about 30 Markdown files.

Constraints that shape the design:

* **Hosting:** Render free web service (512 MB RAM, sleeps when idle) and the Render
  free PostgreSQL 16 database; Vercel for the web apps. The API process already loads
  pandas, NumPy and scikit-learn.
* **Cost:** free and open-source components; no paid API in the MVP.
* **Hard rules carried over from V2:** no fabricated traffic data, routes, ETAs,
  predictions or metrics; never claim untested features.
* **Database images:** `postgis/postgis:16-3.4` (compose and CI) does not include
  pgvector.
* **Tests:** the unit suite runs on SQLite; CI also runs against PostGIS and runs
  `alembic check`.

## Decisions

### D1. The assistant explains and cites; it never computes

The V2 routing engine, OSRM, route ranking, classification, traffic state engine,
weather service and forecast predictor stay authoritative and unchanged. The
assistant reads their outputs (the *facts lane*) and retrieves explanatory text (the
*knowledge lane*). It does not re-rank routes, produce ETAs, estimate traffic, or
forecast. See [RAG_SAFETY.md](RAG_SAFETY.md) for the full boundary list.

### D2. No LLM in the MVP (owner decision, 2026-11-03)

The MVP answer composer is deterministic: templates over facts-lane JSON plus
extractive passages with citations. The code defines an `LLMClient` interface with a
`none` implementation only. Optional adapters (local Ollama, OpenAI-compatible
endpoint) are Phase 4b and stay disabled unless the owner configures them.

### D3. Authenticated users only (owner decision, 2026-11-03)

Every assistant endpoint depends on `current_user` (401 without a resolved user),
not only on `app_access` (which lets anonymous callers through when
`API_AUTH_REQUIRED=false`). This holds even when `API_AUTH_REQUIRED=false` in
development. Admin endpoints use `require_admin`.

### D4. Question retention: 30 days, configurable (owner decision, 2026-11-03)

`rag_queries` stores question text for `RAG_QUERY_RETENTION_DAYS` (default 30), with
no user id. The existing daily retention job (`traffic/maintenance.py::run_retention`)
deletes older rows. Setting the value to 0 disables storing question text (metadata
only). Details in [RAG_SAFETY.md](RAG_SAFETY.md#7-privacy-and-retention).

### D5. Lexical retrieval first: PostgreSQL full-text search

MVP retrieval uses a weighted `tsvector` generated column with a GIN index and
`ts_rank_cd`. No new service, package or model. Embeddings and pgvector are a later,
measured phase with a defined migration path. See [RETRIEVAL_FTS.md](RETRIEVAL_FTS.md).

### D6. Curated, versioned corpus

The MVP corpus is an explicit allowlist of repository documents plus rendered
evaluation summaries, each chunk tagged with its source path, heading path, commit
SHA and the document's stated measurement date. Dynamic sources (published incidents,
verified shortcuts) come later with validity windows. Personal data and unmoderated
community text are never indexed.

### D7. Server-held route plans for explanations

`/v1/routes` gains an optional `plan_id` field. The response is kept in a bounded
in-process TTL cache (15 minutes). `explain-route` reads only that cached copy, so a
client cannot submit altered numbers for the assistant to repeat. A missing or
expired plan returns `410 plan_expired`; the client re-plans. This is the only change
to a V2 response, and it is additive.

### D8. Grounding guard on every answer

Before an answer is returned, a validator checks that every number in it appears in
the facts payload or a cited chunk, that every citation refers to a chunk retrieved
for this request, and that no forbidden claim types are present. With the `none`
composer this is a regression check; with a future LLM it is the main defence. On
failure the deterministic template answer is returned and the event is logged.

### D9. New code is isolated

New package `backend/assistant/` and new tables `rag_documents`, `rag_chunks`,
`rag_queries`, `rag_eval_runs` (Alembic 0004, additive). New routers mount under
`/v1/assistant/*` and `/v1/admin/rag/*`. Existing files touched: router registration in `main.py`, the
`plan_id` hook in `api/routing_api.py`, one optional field in `routing/schemas.py`,
the `rag_queries` cleanup in `traffic/maintenance.py`, and the `tsv` exclusion in
`migrations/env.py`. Nothing else in V2 imports from `assistant/`.

## Alternatives considered

| Option | Why not for the MVP |
|---|---|
| Hosted LLM from the start (free tier of a commercial API) | Owner chose no LLM; terms and limits of free tiers change; external data sharing |
| Self-hosted LLM on Render | 512 MB RAM cannot hold a useful model |
| Dedicated vector database (Qdrant, Chroma, Weaviate) | Extra service with no free host in the current plan; pgvector covers the need later |
| Embeddings from day one (sentence-transformers + torch) | torch alone exceeds the RAM budget; corpus is small and technical, where lexical search is strong |
| Embedding live traffic text | Goes stale within minutes; facts lane reads live data with timestamps instead |
| Letting the client send the route JSON to explain | Client could inject numbers; see D7 |

## Consequences

* The MVP adds no runtime dependency and no paid service.
* Answers are less fluent than an LLM's, but every sentence is traceable.
* Paraphrased questions that share no words with the docs will retrieve poorly until
  Phase 6 (embeddings). A small query-expansion table for Bengaluru place names and
  domain terms mitigates this (see [RETRIEVAL_FTS.md](RETRIEVAL_FTS.md#4-query-processing)).
* Some repository docs contain dated measurements (for example "Status (2026-10-22):
  insufficient data"). The assistant must state the date with such facts. Docs that
  have drifted from the code need updating; that is tracked as a corpus-quality task,
  not hidden by the assistant.
* The in-process plan cache does not survive Render sleeping or a restart. That is
  acceptable for a single free instance; a multi-instance deployment would need a
  shared cache.

## Phase plan (approved direction, 2026-11-03)

| Phase | Scope | Exit check |
|---|---|---|
| 0 | This ADR, safety doc, FTS design, acceptance criteria, evaluation set | Owner approves |
| 1 | `assistant/` package, loaders, chunker, migration 0004, ingest CLI, PostgreSQL FTS and SQLite test retriever | Tests green on SQLite and PostGIS; `alembic check` clean; retrieval metrics reported |
| 2 | `POST /v1/assistant/ask` with the `none` composer, citations, refusals, rate limit, retention | API tests incl. refusal set; citations resolve |
| 3 | `plan_id` + TTL cache; `POST /v1/assistant/explain-route` | Existing routing tests unchanged and green; number-provenance property test |
| 5a | "Why this route?" and Ask panel in `frontend` | Jest + build pass; manual check |
| 4 | Facts tools for current conditions near a place | Fixture tests; stale data labelled; missing data refused |
| 4b | Optional LLM adapters behind the guard | Fake-LLM tests incl. adversarial fabricator blocked |
| 6 | pgvector + embeddings, hybrid retrieval | RSS measured; kept only if metrics improve |
| 7 | Published incidents and verified shortcuts as dynamic corpus | Expired items never retrieved |
| 8 | Optional reranker, admin moderation aid, mobile, deploy | Each gated on measurement or owner go-ahead |

The MVP is Phases 1, 2, 3 and 5a.
