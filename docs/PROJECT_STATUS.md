# Project Status — Bengaluru Pulse V2

_Last updated: 2026‑10‑22 — living resume file._

Branch `v2-build` (local; not pushed). Commits on top of `main`: baseline snapshot
`2e42577` → backend `f7ff3b6` → ML `11c14d8` → web `6b7563d` → mobile/CI/deploy
`61ad452` → docs `f1db377` → final reports.

## Phases

| Phase | State | Evidence |
|---|---|---|
| 0 Audit | ✅ | PROJECT_AUDIT.md, IMPLEMENTATION_ROADMAP.md |
| 1 Foundation | ✅ | settings, redaction, error envelope, health/readiness |
| 2 Routing | ✅ | 3 OSRM graphs; 5 live benchmarks pass |
| 3 Geocoding + navigation UI | ✅ | 68,761-place gazetteer; browser-verified |
| 4 Live ingestion | ✅ | collector running in Docker |
| 5 Database | ✅ | PostGIS, Alembic 0001–0002, restart persistence verified |
| 6 ML | ✅ pipeline / ❌ no model beats baselines | ML_PIPELINE.md |
| 7 Predictive routing | ✅ | TomTom departAt; Pulse forecasts gated |
| 8 Shortcuts/longcuts | ✅ | exhaustive tests + live example |
| 9 Community | ✅ (no real submissions yet) | 9 tests |
| 10 Auth/RBAC | ✅ | 14 tests + live 401/403 |
| 11 Web | ✅ | browser walkthrough |
| 12 Mobile | ✅ builds (APK) / not run on device | TEST_REPORT.md |
| 13 Docker & deployment | ◐ prepared; not public | DEPLOYMENT.md |
| 14 Verification | ✅ local | TEST_REPORT.md |
| 15 Docs | ✅ | docs/ |

## Release audit (2026‑10‑22)

See [RELEASE_READINESS.md](RELEASE_READINESS.md): 115 backend + 7 frontend tests
pass; two defects fixed (TomTom 401 handling; unwritable/unshared model and report
directories); prospective forecast logging (milestone M1) running.

## Next actions (owner)

1. Decide whether to push `v2-build` to `github.com/Isaiah7779/bengaluru-pulse-lite` (public) → CI runs.
2. Create an Oracle Cloud Always Free account and VM; follow DEPLOYMENT.md §3.
3. Confirm TomTom terms for storing observations.
4. Keep the collector running ≥ 14 days, then `python -m forecasting.pipeline segments`.

## Resume notes

* `docker compose up -d` (Docker Desktop must be started first). Web :8080, API :8000.
* Python `.venv-v2`; tests from `backend/`. Use `127.0.0.1` for Postgres on Windows.
* Dev credentials: comments at the end of `backend/.env` (gitignored).
