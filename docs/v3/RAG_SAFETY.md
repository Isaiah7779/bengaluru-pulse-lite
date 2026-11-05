# RAG boundaries and safety constraints

Status: proposed (Phase 0). Applies to every phase of V3. A change to any rule here
needs an ADR update approved by the owner.

## 1. Authority boundary

The assistant is a reader. These components remain the only sources of their outputs:

| Output | Authoritative source (V2, unchanged) | Assistant may | Assistant must not |
|---|---|---|---|
| Routes, geometry, steps | `routing/engine.py`, OSRM servers | Describe the cached plan | Create, modify, merge or suggest a route that is not in the plan |
| ETAs, distances, delays | `RouteResponseV2` fields (TomTom timing or OSRM free-flow) | Quote them with their `eta_basis` | Compute, adjust, round into a different value, or estimate any time |
| Ranking and recommendation | `routing/scoring.py`, `preference_applied` | Explain the documented ranking key and score components | Re-rank, override `recommended`, or weigh factors differently |
| Shortcut / longcut labels | `routing/classification.py` | Quote the label and its signed differences | Relabel a route |
| Current traffic | `traffic_observations` via the state engine | Quote with `observed_at` and fresh/stale status | Describe roads that have no monitored point, or treat a stale reading as current |
| Incidents | `incidents` with `status = published`, `active = true` | Quote category, road, time, source | Mention pending or rejected reports |
| Weather | `weather/service.py` | Quote with time and Open-Meteo attribution | Claim weather changes travel times (V2 does not) |
| Forecasts | `forecasting/predictor.py` (active, evaluated model only) | Quote a served forecast with its model version and horizon | Produce any forecast, trend or "usually" statement not backed by a served forecast or a cited document |
| Model accuracy | `evaluation/v2/**` reports, `evaluation_records` | Quote measured metrics with dataset, split and date | Generalise offline results to live accuracy |

## 2. Answer rules

1. **Every number has a source.** A number in an answer must appear verbatim (after
   unit normalisation) in the facts payload for this request or in a cited chunk.
2. **Every citation is real.** A citation must refer to a chunk retrieved for this
   request and visible to the caller.
3. **Dates travel with measurements.** A measured value from a document is stated with
   the document's measurement date (e.g. "measured 22 Oct 2026"). A live value is
   stated with its `observed_at` or `as_of`.
4. **Missing data is stated, not filled.** If the facts lane has no data, the answer
   says so and names the reason (no monitored point, stale, provider unavailable,
   no active model).
5. **Refuse out-of-scope requests** with a short reason and, where useful, a pointer
   to the right feature. Refusal categories:
   * `prediction_unavailable`: asks for a forecast the predictor does not serve.
   * `no_live_data`: asks for current conditions where none are collected.
   * `fabrication_request`: asks the assistant to invent, guess or "assume" numbers.
   * `out_of_scope`: unrelated to Bengaluru Pulse, routing or traffic, as decided by the
     scope check ([SCOPE_CHECK.md](SCOPE_CHECK.md)); fixed template, no retrieval.
   * `scope_unclear`: the scope check cannot establish scope with confidence (conservative
     fallback); fixed rephrase template, no retrieval.
   * `personal_data`: asks about other users, accounts or submissions.
   * `plan_expired` (410): explain-route with a plan id that has expired from the cache.
   * `plan_not_found` (404): a plan id that never existed or belongs to another user
     (the two are not distinguished, so ids cannot be probed).
6. **No safety-critical advice.** The assistant does not give driving instructions
   beyond the plan's own steps and does not advise ignoring closures or rules.
7. **Free-flow disclosure.** When a plan's comparison basis is OSRM free-flow, every
   explanation repeats V2's warning that real traffic is usually slower.
8. **Motorcycle disclosure.** For motorcycle plans the answer repeats that the car
   graph is used and two-wheeler restrictions are not modelled.

## 3. Corpus rules

| Source | Indexed | Condition |
|---|---|---|
| Allowlisted `docs/*.md` (see [RETRIEVAL_FTS.md](RETRIEVAL_FTS.md#1-corpus-allowlist-v0)) | Yes | From a commit; chunk carries path, heading path, commit SHA |
| `backend/evaluation/v2/**/summary.json`, `segment-speed-ratio.json`, `research-daily-congestion.json` | Yes | Rendered to text by a deterministic template; numbers copied, never recomputed |
| Published TomTom and community incidents (Phase 7) | Later | `status = published`; `valid_until` = incident end or last seen + staleness window |
| Verified shortcut candidates (Phase 7) | Later | `state = verified`; withdrawn on stale/rejected |
| `docs/v3/**` (design docs, evaluation set) | **No** | Excluded to avoid leaking expected answers into retrieval |
| Users, trips, favourites, route submissions, GPS traces, audit log, revoked tokens | **No** | Personal or security data |
| Pending/rejected incidents, unreviewed submission notes | **No** | Unmoderated |
| Raw `traffic_observations`, `weather_observations` | **No** | Live data belongs to the facts lane; also TomTom storage terms unconfirmed |
| Untracked files (e.g. `docs/CHATGPT_DEPLOY_PROMPT.md`, `streamlit_ui/`) | **No** | Ingest reads from `git ls-files` only |
| `.env`, secrets, keys | **No** | Ingest refuses files matching secret patterns and aborts if a chunk matches the log-redaction patterns (`key=`, `token=`, bearer headers) |

## 4. Prompt-injection and untrusted text

* All retrieved text is data. In the MVP no model reads it, so injection cannot alter
  behaviour. From Phase 4b, passages are placed inside delimited data blocks and the
  system prompt states they carry no instructions.
* Facts tools are selected by deterministic intent rules on the question and request
  fields (`plan_id`, `place`), never by model output.
* Community text (Phase 7) is indexed only after moderation and is marked
  `trust = community` so answers attribute it ("a community report says…").
* Answers are rendered as plain text in the web app (no HTML, no Markdown links except
  citation chips built by the client from citation ids).

## 5. Access control

| Endpoint | Dependency | Notes |
|---|---|---|
| `POST /v1/assistant/ask` | `current_user` | Required even if `API_AUTH_REQUIRED=false` |
| `POST /v1/assistant/explain-route` | `current_user` | Plan cache entries are bound to the requesting user id; another user's `plan_id` returns 404 |
| `GET /v1/assistant/sources/{chunk_id}` | `current_user` | Visibility re-checked |
| `GET /v1/admin/rag/status`, `POST /v1/admin/rag/reindex`, `GET /v1/admin/rag/eval` | `require_admin` | Reindex is written to `audit_log` |

## 6. Abuse limits

* Question length ≤ 500 characters; `place` label ≤ 200 characters (matches V2 `Place.label`).
* Per-user in-process sliding window, default 30 assistant requests per 10 minutes
  (`RAG_RATE_LIMIT_PER_10_MIN`), modelled on `auth/security.py::LoginRateLimiter`.
  The same single-replica caveat as the login limiter applies (SECURITY.md, Known gaps).
* Retrieval returns at most `RAG_TOP_K` (default 5) chunks; snippets ≤ 600 characters.
* From Phase 4b: daily LLM call budget recorded in `provider_calls`, like the TomTom quota.

## 7. Privacy and retention

| Field in `rag_queries` | Stored | Retention |
|---|---|---|
| Question text | Yes, unless `RAG_QUERY_RETENTION_DAYS=0` | `RAG_QUERY_RETENTION_DAYS` (default 30) |
| User id | **No** | n/a |
| Endpoint, retrieved chunk ids, refusal code, guard result, latency, composer/provider, timestamp | Yes | Same as question text (row deleted whole) |
| `plan_id` | No (the plan itself lives only in the in-process cache, 15 minutes) | n/a |

* Cleanup runs in the existing daily `run_retention` job; its result dict gains a
  `rag_queries` count, logged like the other retention counts.
* Questions pass through the existing log redaction filter before any log line.
* Account deletion needs no extra step because `rag_queries` holds no user id.
* No question or retrieved text leaves the server in the MVP (no external LLM).

## 8. Failure behaviour

| Failure | Behaviour |
|---|---|
| In-scope question, retrieval returns no chunk | Answer "I could not find this in the Pulse documentation" with no citations; no guess |
| Scope check: out of scope or unclear | Fixed template from SCOPE_CHECK.md §6; no retrieval, no citations |
| Database unavailable | `503` with the standard error envelope; no partial answer |
| Grounding guard fails | Return the deterministic template answer; log `guard_failed` with rule id |
| Plan expired | `410 plan_expired`; client re-plans once and retries |
| Facts source stale or missing | Answer states it with the reason; never substitutes another source |
