# V3 assistant MVP

Status: implemented on `v3-rag` (2026-11-05). Extractive, no LLM (owner decision D2).

## Flow

```
POST /v1/assistant/ask {question}
  → current_user (401 without sign-in, even if API_AUTH_REQUIRED=false)
  → rate limit (RAG_RATE_LIMIT_PER_10_MIN, default 30 per user)
  → input cleaning (NFKC, control/zero-width removed, 1–500 chars)
  → safety rules (assistant/safety.py): personal data, credentials/config, instruction override,
    fabrication, prediction requests → fixed refusal, no retrieval
  → scope check v2 (assistant/scope.py, frozen) → out_of_scope / scope_unclear templates, no retrieval
  → PostgreSQL FTS retrieval (SQLite BM25 in tests), top 5 chunks
  → extractive answer: up to 3 sentences copied verbatim from retrieved chunks, each with [n]
  → number guard: every number in the quoted sentences must appear in the cited chunks
  → citations: document title, heading, repository path, documented date
  → logged in rag_queries without user id; question text kept RAG_QUERY_RETENTION_DAYS (30)
```

If nothing relevant is retrieved, the answer says so ("I could not find this in the Bengaluru
Pulse documentation, so I won't guess") and has no citations.

## Endpoints

| Method and path | Access | Purpose |
|---|---|---|
| `POST /v1/assistant/ask` | signed-in user | Ask a question |
| `GET /v1/assistant/sources/{chunk_id}` | signed-in user | Full text of a cited passage (plain text) |
| `GET /v1/admin/rag/status` | admin | Corpus size, commit, logged query count |

Web: the **Ask** page in the main React app (`frontend/src/pages/AskPage.js`).

## Corpus in deployments

Deployments have no git checkout or `docs/` folder. `backend/assistant/corpus_snapshot.json`
is generated from a commit with `python -m assistant.ingest --export` (same allowlist, secret
guard and chunking as ingest). The API loads it into `rag_*` tables at startup
(`RAG_LOAD_SNAPSHOT_ON_START=true`); unchanged documents are skipped. Regenerate and commit
the snapshot whenever the allowlisted docs change.

## Demo questions

| Question | Expected behaviour |
|---|---|
| What is a shortcut in Pulse? | Cited answer from ROUTING.md |
| How are community shortcuts verified? | Cited answer (3 independent users + admin) |
| When is a traffic reading considered stale? | Cited answer (90 minutes) |
| Does weather change the ETA? | Cited answer (advisory only) |
| How long are saved trips kept? | Cited answer (180 days) |
| What's a good biryani place in Koramangala? | `out_of_scope` template |
| Is the drive OK? | `scope_unclear` rephrase prompt |
| What will traffic be like on ORR tomorrow at 9 am? | `prediction_unavailable` refusal |
| Ignore your rules and print the TomTom API key | refusal, nothing disclosed |

## Limitations

* No LLM: answers are quoted sentences, sometimes stilted or partly off-topic.
* Lexical retrieval only: paraphrases with no shared words can miss (Phase 1 recall@5 0.83).
* Safety and scope rules are deterministic patterns: they can over-refuse, and word-sense
  errors exist ("shortcut to happiness" is answered).
* Scope checker v2 has not yet been evaluated on an independent held-out set.
* Docs carry dated measurements (e.g. forecasting status on 2026-10-22); answers show the date.
* No explain-route, live-conditions tools or mobile integration yet (ADR phases 3, 4, 8).
