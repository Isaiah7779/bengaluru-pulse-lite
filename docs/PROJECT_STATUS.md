# Project Status — Bengaluru Pulse V2

_Last updated: 2026-10-22 — living resume file._

Branch `v2-build` (local only; not pushed). Commits: `2e42577` baseline snapshot →
`f7ff3b6` backend → `11c14d8` ML → `6b7563d` web app.

## Phase progress

| Phase | State | Evidence |
|---|---|---|
| 0 Audit | ✅ | PROJECT_AUDIT.md, IMPLEMENTATION_ROADMAP.md |
| 1 Foundation | ✅ | core/ settings, redacting logs, safe errors, /health, /health/ready |
| 2 Routing | ✅ | car/foot/bicycle OSRM graphs; 5 benchmark trips pass live (tests/test_integration_live.py) |
| 3 Geocoding + nav UI | ✅ | 68,761-place OSM gazetteer; browser-verified search/GPS/map-pick |
| 4 Live ingestion | ✅ | collector container running (TomTom flow 26 pts/30 min, incidents hourly, Open-Meteo) |
| 5 Database | ✅ | PostGIS + Alembic 0001/0002, verified upgrade/check/downgrade on fresh DB |
| 6 ML | ✅ (honest negative result) | research track evaluated; operational track gated on ≥14 days of data |
| 7 Predictive routing | ✅ | TomTom departAt prediction; Pulse forecasts only from an activated model |
| 8 Shortcut/longcut | ✅ | exhaustive tests; live shortcut observed (Whitefield→E-City) |
| 9 Community | ✅ | validation, map matching, ≥3 independent confirmations, admin-only verify |
| 10 Auth/RBAC | ✅ | 14 RBAC tests; live 401/403 checks; admin bootstrap CLI |
| 11 Web | ✅ | browser walkthrough (anon, user, admin, mobile width) |
| 12 Mobile | ⏳ next | |
| 13 Docker/deploy | ◐ | compose stack healthy locally; public deployment blocked on owner accounts |
| 14 Verification | ◐ | backend 96 + frontend 7 tests passing; failure-injection pending |
| 15 Docs | ⏳ | |

## Running locally

```bash
docker compose up -d   # postgres, osrm-car/foot/bicycle, backend, collector, frontend
```
Web: http://localhost:8080 · API: http://localhost:8000/docs.
Local dev admin/user credentials: comments at the end of `backend/.env` (gitignored).

## Blockers needing the owner

* Public hosting accounts (Oracle Cloud Always Free recommended; see DEPLOYMENT.md).
* TomTom data-storage terms confirmation before publishing any collected dataset.
* Forecasting on collected data needs ≥14 days of collection (started 2026-10-22 03:16 UTC).
