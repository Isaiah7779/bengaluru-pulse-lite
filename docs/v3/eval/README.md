# V3 evaluation set (v0)

`golden_v0.jsonl` holds 78 questions written on 2026-11-03 from the documentation
at commit `fac06c3`. It is never indexed by the assistant (see
[RAG_SAFETY.md](../RAG_SAFETY.md#3-corpus-rules)).

| Expected behaviour | Items | Phase first scored |
|---|---|---|
| `answer` (docs Q&A with citations) | 53 | 1 (retrieval), 2 (answers) |
| `explain_route` (cached plan fixtures) | 6 | 3 |
| `facts` (current conditions, fixtures) | 2 | 4 |
| `refuse` | 17 (2 explain-route, 1 live-conditions, 14 ask) | 2, 3, 4 |

Categories: routing method 13, traffic data 9, forecasting 9, explain route 8,
classification 6, user guide 6, security and privacy 6, community 4, out of scope 4,
live conditions 3, prediction refusals 3, fabrication refusals 3, personal-data
refusals 2, prompt injection 2. Phrasing deliberately mixes formal and casual
English ("why do i only see 5 routes max?") and local names (ORR, Silk Board, KIA).

## Item fields

| Field | Meaning |
|---|---|
| `id` | Stable id; never reused after an item is removed |
| `category`, `phase` | Grouping and the phase in which it is first scored |
| `question` | User text, sent as-is |
| `expected_behavior` | `answer`, `explain_route`, `facts` or `refuse` |
| `refusal_code` | For `refuse`: one of the codes in [RAG_SAFETY.md](../RAG_SAFETY.md#2-answer-rules) |
| `expected_sources` | `{path, heading_prefix}`; a retrieved chunk matches if its source path is equal and its heading path starts with the prefix (after normalisation) |
| `must_include` | Phrases that must appear in the answer; each was checked to occur in a cited section |
| `must_not_include` | Phrases that must not appear |
| `must_state_date`, `must_state_as_of` | The answer must carry the document's measurement date / the fact's timestamp |
| `fixture` | For plan and facts items: the plan or data shape the test builds (Phase 3/4 fixtures, never real provider data) |
| `must_reference_fields` | For plan items: plan fields whose values must appear in the explanation |
| `must_include_template` | A named fixed sentence that must appear (e.g. `free_flow_warning`) |
| `status` | Optional; `blocked_by_doc_drift` = excluded from scoring until the docs are fixed (no item has it in v0) |
| `notes` | Reviewer notes |

Normalisation for matching: Unicode NFKC, U+2010/U+2011 hyphens mapped to `-`,
whitespace collapsed, case-insensitive.

## Metrics

Computed over scored items only, on PostgreSQL.

| Metric | Definition |
|---|---|
| recall@5 | Share of `answer` items with at least one expected source among the top 5 chunks |
| MRR | Mean of 1 / rank of the first matching chunk (0 if none in the top 10) |
| Out-of-scope rejection | Share of `out_of_scope` items with no chunk above `RAG_MIN_SCORE` |
| Grounding violations | Count of answers containing a number not present in the facts payload or cited chunks |
| Citation validity | Share of citations that were retrieved for the request and resolve |
| Refusal correctness | Share of `refuse` items returning the expected `refusal_code` |
| False refusals | Share of `answer` items that were refused |
| Phrase pass rate | Share of items meeting all `must_include` / `must_not_include` / date rules |

Targets live in [ACCEPTANCE_CRITERIA.md](../ACCEPTANCE_CRITERIA.md).

## Self-check done in Phase 0

A script (run outside the repo) parsed every line as JSON, checked ids are unique,
checked every `refuse` item has a code, resolved every `expected_sources` heading in
the cited file, and confirmed every `must_include` phrase occurs in the cited sections.
Result on 2026-11-03: 78 items, no problems. Phase 1 adds this as a pytest so the set
cannot drift from the docs unnoticed.

## Corpus drift found while writing the set

Found on 2026-11-03 and corrected the same day (owner-approved docs fix):

1. `USER_GUIDE.md` §1 said routes need no account, and the `SECURITY.md` authorization
   table allowed anonymous route planning. In fact `API_AUTH_REQUIRED=true` is the default
   (`core/settings.py`, `docker-compose.yml`, `render.yaml`), `app_access` returns 401,
   and the web and mobile apps show only the sign-in screen. Both docs now say so;
   SP-06 is scored again.
2. `SECURITY.md` said there is no e-mail verification or password reset; that holds only
   for built-in accounts, not Firebase sign-in. Corrected; SP-04 updated.
3. `RESULTS_AND_LIMITATIONS.md`, `README.md`, `DEPLOYMENT.md`, `DEPLOYMENT_GUIDE.md` and
   `PROJECT_STATUS.md` now state that the free-tier configuration exists and that no
   public deployment has been verified.
4. `ROUTING.md` and `ARCHITECTURE.md` now note the configurable corridor limits and that
   avoid options are not offered on public OSRM servers (RT-13 cites both).

Still open, by design: forecasting status in `ML_PIPELINE.md` and
`RESULTS_AND_LIMITATIONS.md` is dated 2026-10-22 and says the first evaluation becomes
possible around 2026-11-05. Answers must keep the date (FC-01 has `must_state_date`);
from Phase 4 the live status comes from `forecasting.predictor.active_model()` instead.

Dated records (`TEST_REPORT.md`, `RELEASE_READINESS.md`, `FINAL_*.md`,
`PRESENTATION_OUTLINE.md`, `SUBMISSION_CHECKLIST.md`, `IMPLEMENTATION_ROADMAP.md`,
`PROJECT_AUDIT.md`) still say "not publicly deployed" as of 22 Oct 2026. They are
historical snapshots, are not in the corpus allowlist, and were left unchanged.

## Changing the set

Add items with new ids, keep old ids stable, bump the file name (`golden_v1.jsonl`)
when items are removed or expectations change, and record each version's metrics
separately in `rag_eval_runs`.
