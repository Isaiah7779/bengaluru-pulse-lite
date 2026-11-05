# Retrieval design: PostgreSQL full-text search, then embeddings

Status: proposed (Phase 0). Phase 1 implements sections 1–6; section 7 is the
Phase 6 migration path.

## 1. Corpus allowlist (v0)

Ingest reads only files tracked by git (`git ls-files`) at the current commit.

| Source | Why included |
|---|---|
| `docs/ROUTING.md` | Candidate generation, ranking, classification, evidence rules |
| `docs/TRAFFIC.md` | Sources, coverage, quota, ingestion, staleness |
| `docs/ML_PIPELINE.md` | Forecasting method, gate, measured results |
| `docs/RESULTS_AND_LIMITATIONS.md` | Measured results with evidence labels, limitations |
| `docs/RESEARCH_MILESTONE_FORECASTING.md` | Prospective evaluation definitions |
| `docs/USER_GUIDE.md` | How to use the apps |
| `docs/SECURITY.md` | Auth, roles, limits |
| `docs/DATABASE.md` | Tables, retention, privacy |
| `docs/ARCHITECTURE.md` | Components, request lifecycle |
| `docs/DEPLOY_FREE_TIER.md` | Free-tier limits users will notice |
| `backend/evaluation/v2/segment-speed-ratio.json` | Current status of the operational forecasting task |
| `backend/evaluation/v2/research-daily-congestion.json` | Offline results on the public dataset |

Excluded on purpose: process and submission documents (`PROJECT_AUDIT.md`,
`SUBMISSION_CHECKLIST.md`, `DEMO_SCRIPT.md`, `PRESENTATION_OUTLINE.md`,
`IMPLEMENTATION_ROADMAP.md`, `PROJECT_STATUS.md`, `RELEASE_READINESS.md`,
`FINAL_*`, `TEST_REPORT.md`, `DEPLOYMENT*.md` except the free-tier guide,
`AUTHENTICATION.md`), all of `docs/v3/`, and anything untracked. The list lives in
code (`assistant/corpus.py`) and is covered by a test, so adding a source is a reviewed change.

## 2. Chunking

1. Parse Markdown into sections by heading (`#` to `###`). The heading path
   ("ROUTING.md › Shortcut / longcut classification") is kept with each chunk.
2. Keep tables and fenced code blocks whole. A table larger than the window is split
   by rows, and the header row is repeated in each piece.
3. Pack paragraphs into windows of about 350 words (a stand-in for ~400 tokens, so no
   tokenizer dependency). Overlap is by whole paragraph: a last paragraph of ≤ 50 words
   is carried into the next window; tables and code blocks are never carried. Never
   cross a section boundary.
4. Extract the document's measurement date if the section states one (patterns such
   as `measured 2026-10-22`, `(2026‑10‑22)`, `22 Oct 2026`); store it as `measured_on`.
5. JSON evaluation reports are rendered by fixed templates into one chunk per task and
   horizon, e.g. "Task segment_speed_ratio: status insufficient_data; reason …;
   generated 2026-10-22". Every value is copied from the file.
6. `content_hash = sha256(normalised text)`. Re-ingest upserts by
   `(document_id, ordinal)` and skips unchanged hashes, so it is idempotent.

Normalisation before hashing and indexing: Unicode NFKC, then map U+2010/U+2011 to
`-` (the docs use non-breaking hyphens such as `2026‑10‑22`, which NFKC alone does not
turn into ASCII), collapse whitespace, keep case for display.

## 3. Schema (Alembic 0004, additive)

```sql
CREATE TABLE rag_documents (
  id            serial PRIMARY KEY,
  source_type   varchar(32)  NOT NULL,   -- doc | eval_report | incident | shortcut
  source_ref    varchar(256) NOT NULL,   -- path or table:id
  title         varchar(200) NOT NULL,
  commit_sha    varchar(40),
  content_hash  varchar(64)  NOT NULL,
  visibility    varchar(16)  NOT NULL DEFAULT 'user',  -- user | admin
  ingested_at   timestamptz  NOT NULL,
  UNIQUE (source_type, source_ref)
);

CREATE TABLE rag_chunks (
  id            serial PRIMARY KEY,
  document_id   int NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
  ordinal       int NOT NULL,
  heading_path  varchar(400) NOT NULL,
  body          text NOT NULL,
  measured_on   date,
  valid_from    timestamptz,
  valid_until   timestamptz,
  content_hash  varchar(64) NOT NULL,
  meta          json,
  UNIQUE (document_id, ordinal)
);
-- PostgreSQL only (same pattern as the PostGIS columns in 0001):
ALTER TABLE rag_chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(heading_path, '')), 'A') ||
    setweight(to_tsvector('english', body), 'B') ||
    setweight(to_tsvector('simple',  body), 'D')
) STORED;
CREATE INDEX ix_rag_chunks_tsv ON rag_chunks USING gin (tsv);
CREATE INDEX ix_rag_chunks_valid ON rag_chunks (valid_until);
```

* `'english'` stems words ("ranked" ↔ "ranking"); the extra `'simple'` vector keeps
  unstemmed tokens such as `osrm`, `tomtom`, `least_traffic_now`, `frc5`.
* The generated column and GIN index are created only when the dialect is PostgreSQL,
  and excluded from autogenerate comparison the same way the PostGIS `geog` columns
  are: `migrations/env.py::include_object` gains `name == "tsv"` (column) and the
  `_tsv` index suffix, so `alembic check` stays clean on both. Phase 1 confirms this in CI.
* `rag_queries` and `rag_eval_runs` are plain tables (see [RAG_SAFETY.md](RAG_SAFETY.md#7-privacy-and-retention)).

## 4. Query processing

1. Normalise (NFKC, lower case, strip punctuation except `_` and `-`), max 500 characters.
2. **Domain expansion table** (`assistant/synonyms.py`, reviewed list, no learning).
   Examples: `kia` → `airport`; `orr` → `outer ring road`; `eta` → `travel time`;
   `jam`, `traffic jam` → `congestion delay`; `short cut` → `shortcut`; `quicker` →
   `faster`. PostgreSQL thesaurus dictionaries need files on the database server,
   which Render's managed Postgres does not allow, so expansion happens in the app.
3. Build two queries:
   * strict: `websearch_to_tsquery('english', q)` (AND of terms, supports quotes);
   * loose: OR of the stemmed lexemes of the question and its expansions.
4. Run strict first; if it returns fewer than `RAG_TOP_K` rows, fill from loose.

## 5. Ranking and filtering

```sql
SELECT c.id, c.heading_path, d.source_ref, c.measured_on,
       ts_rank_cd(c.tsv, :q, 32) AS score,
       ts_headline('english', c.body, :q, 'MaxWords=60, MinWords=20') AS snippet
FROM rag_chunks c JOIN rag_documents d ON d.id = c.document_id
WHERE c.tsv @@ :q
  AND d.visibility = ANY(:visible)
  AND (c.valid_until IS NULL OR c.valid_until > now())
ORDER BY score DESC
LIMIT :k;
```

* Normalisation flag 32 maps rank into 0–1 (`rank / (rank + 1)`). **No score floor is
  used.** Phase 1 measured that no floor separates out-of-scope questions from real ones
  ([PHASE1_RESULTS.md](PHASE1_RESULTS.md)), so scope is decided before retrieval by the
  deterministic check in [SCOPE_CHECK.md](SCOPE_CHECK.md) (owner decision, 2026-11-03).
  An in-scope question with no matching chunk gets the "not found" answer.
* Tie-break: shorter chunk first, then lower ordinal (earlier in the document).
* At most 2 chunks per document in the top 5, so one long document does not crowd
  out others.

## 6. SQLite path (unit tests only)

SQLite has no `tsvector`. A small in-Python BM25 (k1 = 1.2, b = 0.75) over the same
`rag_chunks` rows, with the same tokenizer and expansion table, implements the same
`Retriever` interface. It exists so the API and pipeline can be tested without
Postgres. **Retrieval quality is measured only on PostgreSQL** (CI has a PostGIS
service); SQLite results are never reported as metrics.

## 7. Migration path to embeddings and hybrid retrieval (Phase 6)

Each step can be shipped and rolled back on its own. `RAG_RETRIEVAL_MODE`
(`lexical` | `hybrid`, default `lexical`) selects the path at runtime.

| Step | Change | Check before the next step |
|---|---|---|
| 6.1 | Confirm pgvector on the target databases: run `SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector'` on Render free Postgres | Row present. If absent, stop and choose between staying lexical or another host (owner decision) |
| 6.2 | Database image for CI and compose: `infrastructure/postgres/Dockerfile` = `postgis/postgis:16-3.4` plus the pgvector package for PostgreSQL 16; switch `docker-compose.yml` and `ci.yml` to it | Existing PostGIS tests and `alembic check` still pass |
| 6.3 | Migration 0005: `CREATE EXTENSION IF NOT EXISTS vector` (PostgreSQL only); `rag_chunks.embedding vector(384)` nullable; `embedding_model varchar(64)`; HNSW index `vector_cosine_ops` | Upgrade/downgrade round trip on fresh PostGIS; SQLite unaffected |
| 6.4 | Offline embedding job: `python -m assistant.embed` with `BAAI/bge-small-en-v1.5` (384 dims, MIT licence) through `fastembed` (ONNX Runtime, no torch); writes vectors for chunks whose `embedding_model` differs | Runs locally or in GitHub Actions, never in the web process |
| 6.5 | Query-time embedding behind `RAG_RETRIEVAL_MODE=hybrid`, model loaded lazily on first use | Measure backend RSS in a 512 MB-limited container (`docker run -m 512m`) before and after; cold-start time recorded |
| 6.6 | Hybrid ranking: lexical top 20 and vector top 20 fused with reciprocal rank fusion (k = 60), then the same filters and per-document cap | Evaluation set: hybrid kept only if it meets the Phase 6 criteria in [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md#phase-6-embeddings-gate) |
| 6.7 | Rollback | Set `RAG_RETRIEVAL_MODE=lexical`; the vector column stays nullable and unused |

SQLite tests for hybrid mode store vectors as JSON and use NumPy cosine similarity
with a fake deterministic embedder, so no model download happens in CI unit tests.

Re-embedding rule: changing the embedding model changes `embedding_model`; the job
re-embeds every chunk and the old vectors are not mixed with new ones at query time.
