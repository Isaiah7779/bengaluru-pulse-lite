# Bengaluru Pulse — Phase 0 Project Audit

Audit date: 2026-10-22. Branch `v2-build`, baseline commit `2e42577` (snapshot of
the pre-existing uncommitted work so nothing is lost).

Every statement below was checked by reading code or running a command on this
machine. "Verified" means a command was executed and its output inspected.

## 1. Environment (verified)

| Item | Finding |
|---|---|
| Host | Windows 11, 8 logical CPUs, 14.8 GB RAM |
| Python | `.venv-v2` = Python 3.12 (fastapi 0.142, pydantic 2.13, scikit-learn 1.9.1, pandas 3.0). System Python is 3.13. |
| Node | v22.18, npm 10.9 |
| Docker | Docker Desktop 29.7.2; daemon is **not running by default** (started manually during audit; 7 GB allocated to the VM) |
| PostgreSQL | Not installed locally (`psql` missing) — must run in Docker |
| OSRM image | `ghcr.io/project-osrm/osrm-backend:latest` present locally |

## 2. Architecture as found

```
React (CRA, 3,738-line App.js) ──axios──> FastAPI main.py (flat module layout)
                                             ├── services.py  (ML model, "forecast", hotspots, TomTom calls)
                                             ├── database.py  (SQLite: one `predictions` table)
                                             └── routing/      (OSRM client + RoutingService + TomTom route ETA)
OSRM (Docker, optional profile) ── graph in data/osm/bengaluru.osrm.*
```

Empty placeholder modules exist: `forecasting/{baseline,features,predictor}.py`,
`traffic/{collector,state_engine}.py`.

## 3. Feature-by-feature status

### Routing (Phase 2 scope)
* **Full Bengaluru OSRM MLD graph exists and works** (verified): started
  `osrm-routed --algorithm mld` on `data/osm/bengaluru.osrm`; RSS ≈ 300 MB;
  graph ≈ 540 MB on disk; built from `bengaluru.osm.pbf` (52 MB).
* Required test trips all route successfully (snap distance ≤ 47 m):

  | Trip | Primary (km / free-flow min) | OSRM native alternatives |
  |---|---|---|
  | Whitefield → Marathahalli | 7.6 / 7.5 | 0 |
  | Whitefield → Electronic City | 24.7 / 28.7 | 1 |
  | Indiranagar → Yeshwanthpur | 14.7 / 17.2 | 1 |
  | Airport (KIA) → Whitefield | 38.0 / 38.2 | 2 |
  | Koramangala → Hebbal | 15.3 / 20.9 | 1 |

  OSRM's native alternatives are sparse → corridor-based candidate generation is needed (it exists).
* **Vehicle profiles: only `car.lua` was built.** Verified that
  `/route/v1/foot/...` on this server returns the *identical car route*
  (`weight_name: routability`) — OSRM ignores the URL profile name. Today
  `route_profiles.py` honestly labels non-car modes `fallback_to_car`, but the
  API still returns car routes for walking/bicycle requests. **Must be fixed by
  building `foot.lua` and `bicycle.lua` graphs** (motorcycle: no stock OSRM
  profile; car graph + documented limitation).
* `RoutingService` (routing/route_service.py): corridor waypoint candidates (10
  lateral offsets), strict shortcut/longcut classification with a 5 % margin,
  TomTom ETA applied *only* to the reference route (honest), scoring
  `eta + 0.35·km + 0.25·delay`.
  * Gaps: deduplication compares only distance/duration (not geometry);
    corridor requests run sequentially (10 serial HTTP calls); no departure
    time, no preferences, no avoid options; candidates other than the reference
    get no traffic estimate; route_score mixes units without configuration.
* `docker-compose.yml` OSRM service is **broken**: mounts empty `data/osrm/`
  and uses `osrm/osrm-backend:v5.27.1` while the graph was produced with the
  `ghcr.io/project-osrm/osrm-backend:latest` toolchain (file-format mismatch risk).

### Traffic, weather, incidents
* TomTom key present in `backend/.env` (32 chars; never printed). Verified a live
  Flow Segment request: HTTP 200 (Marathahalli Bridge, 29 vs 35 km/h free-flow).
* Open-Meteo verified reachable (HTTP 200, current Bengaluru weather). **Not
  integrated anywhere in the code.**
* `/api/live-traffic` and `/api/live-traffic/bengaluru` call TomTom live (genuine).
* **Fabricated data (violates project rules):**
  * `/forecast`, `/hotspots`, `/analytics`, `/historical-trends` compute values
    from a hand-written formula (`domain.compute_congestion`) plus
    `random.uniform` noise and present them as forecasts/trends.
  * `/incidents` falls back to `_simulate_incidents()` (random incidents) because
    the configured ASTraM URL is just `https://karnataka.gov.in` (not a feed).
* No collector, no scheduling, no persistence of observations.

### ML
* Datasets: `Banglore_traffic_Dataset.csv` (8,936 rows, **daily** granularity,
  2022-01-01 → 2024-08-09, 16 road segments, ~9 rows/day — not every road every
  day). Public Kaggle-style dataset with undocumented provenance; values such as
  congestion = 100.0 and identical TTI suggest possible synthesis — must be stated
  as a limitation. `traffic_dataset.csv` is a 492-row subset.
* Model: `traffic_model_tuned.pkl` (RandomForest). Reported R² 0.958, MAE 4.04,
  RMSE 5.15 — **from a random `train_test_split` on 492 rows** with *contemporaneous*
  `Average Speed` and `Traffic Volume` as inputs. This is a same-day estimation
  (nowcast) model, not a forecast, and the random split leaks temporal
  information. These metrics cannot be cited as forecasting accuracy.
* Pickles were saved with scikit-learn 1.7.2 / 1.8.0; venv runs 1.9.1
  (`InconsistentVersionWarning`); `requirements.txt` pins 1.7.2 → reproducibility issue.
* No baselines, no chronological evaluation, no model registry, no GNN.

### Database / persistence
* SQLite `traffic.db` with a single `predictions` table; the file is **committed to git**.
* No PostgreSQL/PostGIS, migrations, users, trips, observations or spatial indexes.

### Authentication / authorization
* **None.** No users, no login, no roles. All endpoints public. CORS
  `allow_credentials=True` with configurable origins.

### Frontend
* CRA (react-scripts 5) + React 19, Leaflet + react-leaflet, recharts/chart.js,
  framer-motion, and an unused `@react-google-maps/api` dependency.
* `App.js` is 3,738 lines; it renders the fabricated hotspot/forecast/trend data
  as if real. Route planning uses `/routing/route` with lat/lon of 6 fixed
  locations — **no geocoding, no free-text search, no GPS, no map picking**.
* Tests: 1 smoke test (passes, 89 s).

### Mobile
* **No mobile code exists.**

### Docker / CI / deployment
* `backend/Dockerfile` (python:3.11-slim) OK in shape; but `backend/.dockerignore`
  excludes `*.csv` (training data absent in image — fine for inference) and the
  compose OSRM service is broken (above).
* `frontend/Dockerfile` + nginx proxy `/api/` → backend: reasonable.
* `.github/workflows/ci.yml`: runs unittest + CRA test/build. Uses Python 3.11
  while pickles need sklearn compatibility; no lint, no Docker build check.
* No deployment exists. No public URL. `docs/DEPLOYMENT.md` is local only.

### Tests (verified baseline)
* Backend: `pytest` → **6 passed** (10 sklearn version warnings).
* Frontend: `react-scripts test` → **1 passed**.

## 4. Security & configuration issues

1. No authentication or authorization at all.
2. `backend/traffic.db` (runtime data) tracked in git.
3. `/api/live-traffic*` error responses echo raw exception text (`detail=f"...{exc}"`),
   which can leak the request URL — **including the TomTom key in the query string**.
4. Unbounded TomTom usage: every route request calls TomTom; `/api/live-traffic/bengaluru`
   issues one call per point per request with no caching → a single visitor can exhaust
   the 2,500/day free quota.
5. `requirements.txt` unpinned except scikit-learn (pin conflicts with actual pickles).
6. Pydantic v1-style `@validator` (deprecated in v2).
7. `.env` correctly gitignored (verified `git check-ignore`).
8. `MEM_BRAIN_*` variables in `.env` are unused by the code.

## 5. External constraints verified (2026-10-22, web research)

| Service | Verified constraint | Consequence |
|---|---|---|
| TomTom | 2,500 free non-tile requests/day, tiles 50k/day; above cap blocked (Freemium) | Collector + routing must share a strict daily budget with caching |
| TomTom terms | Could not locate an explicit storage/caching clause | Treat collected observations as private research data; do not redistribute raw TomTom data; flag in docs |
| Open-Meteo | Free, no key, non-commercial use | Use for weather; attribute |
| Nominatim (OSMF) | Autocomplete forbidden; 1 req/s | Not used for suggestions |
| Photon (komoot) | Public, designed for search-as-you-type, "be fair" | Optional fallback only |
| Hugging Face Spaces | Docker Spaces now require a paid plan | Not usable at ₹0 |
| Render free | Spins down after 15 min, no persistent disk, ~512 MB RAM, free Postgres expires after 30 days | Cannot host OSRM + backend reliably; DB unsuitable |
| Koyeb free | 1 instance, 512 MB RAM, 0.1 vCPU | Backend only, no OSRM |
| Neon free | 0.5 GB storage, 100 CU-h/month, PostGIS available, scale-to-zero | Viable DB with retention policy |
| Oracle Always Free | Ampere A1 reportedly reduced to 2 OCPU / 12 GB (June 2026); idle reclaim rules; card verification at signup | Only verified ₹0 option able to host OSRM (3 profiles) + backend + PostGIS on one VM |
| GCP e2-micro | 1 GB RAM, US regions only, card required | Marginal for OSRM car only |

## 6. Summary verdict

A credible routing core exists on a complete Bengaluru graph, plus a working TomTom
integration. Everything labelled "forecast", "trend", "hotspot" and the incident
fallback is fabricated and must be replaced with collected data or honest
"unavailable" states. Walking/cycling routing is actually car routing. There is no
database, auth, geocoding, data collection, valid forecasting evaluation, mobile
app or deployment. See `IMPLEMENTATION_ROADMAP.md`.
