# Implementation Roadmap — Bengaluru Pulse V2

Derived from `PROJECT_AUDIT.md`. Principle: a coherent, verifiable navigation
product over a large codebase. Nothing fabricated; every metric shown comes from
a backend response that traces to OSRM, TomTom, Open-Meteo, OSM, stored
observations or an evaluated model.

## Target architecture

```
           Web (React)            Mobile (Expo / React Native)
                 \                    /
                  HTTPS  /api  (JWT bearer)
                          |
                   FastAPI backend ─────────────┐
   routers: health, geocode, routes, traffic,   │
   weather, incidents, forecasts, auth, me,     │
   community, admin, legacy                     │
                          │                     │
     ┌──────────┬─────────┼───────────┐         │
  OSRM car   OSRM foot  OSRM bicycle  PostgreSQL+PostGIS (SQLAlchemy + Alembic)
  (MLD graphs built once, persistent volume)    │
                                                │
   Collector worker (same image, separate process): TomTom flow + incidents,
   Open-Meteo weather → validated, de-duplicated, timestamped observations
                                                │
   ML pipeline (offline CLI): validate → features → baselines → models →
   chronological evaluation → model_versions + evaluation records
```

Key design choices:
* **Backend package layout** kept flat-compatible: new sub-packages `core/`, `db/`,
  `auth/`, `providers/`, `geocoding/`, `community/`, `api/`; existing `routing/`,
  `traffic/`, `forecasting/` filled in. `main.py` keeps working legacy endpoints.
* **Database:** SQLAlchemy 2 ORM; portable columns (lat/lon numerics, GeoJSON) +
  PostGIS `geography` generated columns and GiST indexes created by Alembic on
  PostgreSQL only. SQLite remains for unit tests and zero-dependency local dev.
* **Auth:** bcrypt password hashes, short-lived JWT access tokens with `jti`,
  server-side revocation on logout, role column (`user`/`admin`) never writable
  through public APIs; admin bootstrap by CLI using env/stdin, no default creds.
* **Geocoding:** self-hosted gazetteer extracted from the local OSM PBF (named
  places, POIs, shops, landmarks, localities, streets) stored in the DB; Photon as
  optional fallback; coordinate parsing; reverse geocoding from the gazetteer.
* **Traffic budget:** central TomTom quota guard (default 2,000/day of the 2,500
  free) shared by collector and routing; response caching.
* **Vehicle modes:** separate OSRM graphs for car, foot, bicycle. Motorcycle uses
  the car graph and is explicitly labelled as such (no stock OSRM motorcycle profile).
* **Predictions:** future-departure ETAs use (a) TomTom's departAt (provider's
  historical-profile prediction, labelled as provider prediction) and (b) our own
  model only where it has passed chronological evaluation against baselines.

## Phases, deliverables and exit criteria

| # | Phase | Deliverables | Exit criteria |
|---|---|---|---|
| 1 | Foundation | `core/settings.py` (pydantic-settings), structured logging, error handler that never leaks secrets, `/health` + `/health/ready` with dependency checks, pinned requirements, pytest config, remove fabricated endpoints' fake data | Tests pass; key-leak regression test |
| 2 | Bengaluru routing | Fixed compose OSRM; foot & bicycle graphs; parallel corridor candidates; geometry-aware dedup (sampled Hausdorff / overlap); navigation steps; the 5 benchmark trips as integration tests | Benchmarks pass against live OSRM; mode honesty tests |
| 3 | Geocoding + frontend navigation | Gazetteer build script + `/geocode/search`, `/geocode/reverse`; frontend search box, suggestions, GPS, map-click picking, route display, steps, errors | Manual + automated UI test |
| 4 | Live ingestion | `providers/` (TomTom flow, TomTom incidents, Open-Meteo); validation, dedup, staleness; collector with bounded frequency + quota guard | Collector run persists real rows |
| 5 | Database | Alembic migrations, PostGIS, models (users, sessions, observations, weather, incidents, segments, routes/trips, favourites, community, model_versions, evaluations, predictions), retention job | Migration test on Postgres; restart persistence check |
| 6 | ML | Reproducible pipeline; persistence + historical-average baselines; GBM; chronological split; MAE/RMSE/MAPE per horizon; registry; collected-data pipeline (15/30/60 min horizons) gated on data volume | Metrics recorded from actual runs |
| 7 | Predictive routing | Preferences (fastest/shortest/least current traffic/least predicted traffic/balanced), avoid tolls/highways/ferries where engine supports, departure time, scoring config, evidence explanations, graceful degradation | Unit + integration tests |
| 8 | Shortcuts/longcuts | Exact definitions, comparable ETA basis, missing/equal handling, explanation text | Exhaustive classification tests |
| 9 | Community | Submissions (GPS trace), OSRM map matching, validation checks, moderation, lifecycle candidate→under_review→verified/rejected/stale, ≥3 independent confirmations | Lifecycle tests |
| 10 | Auth & RBAC | Register/login/logout/profile, favourites, trip history, admin user mgmt, freshness, model metrics, system health | Authorization tests incl. self-promotion & IDOR |
| 11 | Web experience | Map-centred responsive UI, route comparison, traffic, predictions, weather, incidents, departure planning, history, dashboards | Build + tests + browser walkthrough |
| 12 | Mobile | Expo app (GPS, search, routes, traffic, predictions, explanations, submissions) | `expo export` bundle succeeds; typecheck |
| 13 | Docker & deployment | Compose with PostGIS, 3 OSRM services, collector, healthchecks, volumes, Caddy/HTTPS option; CI with Postgres service + Docker build; free-tier deployment plan | `docker compose up` healthy locally; CI config validated |
| 14 | Verification | All suites, end-to-end workflow, failure injection (OSRM down, TomTom down, unauthorized admin) | TEST_REPORT with real output |
| 15 | Release docs | ARCHITECTURE, ROUTING, TRAFFIC, ML_PIPELINE, DATABASE, SECURITY, TEST_REPORT, DEPLOYMENT, RESEARCH, PROJECT_STATUS, FINAL_SYSTEM_AUDIT | Implemented / tested / deployed / externally-verified distinguished |

## Known blockers requiring the owner

1. **Public deployment** needs accounts the owner must create (agents may not create
   accounts): recommended Oracle Cloud Always Free VM (whole stack incl. OSRM) or,
   split, Neon (DB) + Render/Koyeb (API, no OSRM) + GitHub/Cloudflare Pages (web).
2. **Historical traffic depth** only grows with time; forecasting on collected data
   needs weeks of collection before meaningful evaluation.
3. **TomTom data storage terms** should be confirmed by the owner before publishing
   any dataset derived from TomTom.
