# Test report

All results below were produced on 2026‑10‑22 on the development machine
(Windows 11, 8 CPUs, 14.8 GB RAM, Docker Desktop 29.7, Python 3.12, Node 22.18)
with the local Docker Compose stack running, unless stated otherwise. After `v2-build`
was pushed, GitHub Actions CI ran once on commit `6b37482` and passed all four jobs
(backend, frontend, mobile, docker):
https://github.com/Isaiah7779/bengaluru-pulse-lite/actions/runs/39756763914.

## R4 verification run (22 Oct 2026, 08:38–08:45 UTC)

| Check | Command | Exact outcome |
|---|---|---|
| Backend suite | `cd backend && python -m pytest -q` | **115 passed**, 0 failed, 0 skipped, 2 warnings (95.8 s) |
| Frontend tests | `CI=true npx react-scripts test --watchAll=false` | **7 passed** |
| Frontend build | `CI=true npm run build` | compiled successfully (221.93 kB JS, 9.16 kB CSS, gzipped) |
| Mobile typecheck | `npx tsc --noEmit` | 0 errors |
| Running app via nginx | `GET http://localhost:8080/`, `/api/health/ready`, `POST /api/v1/routes` | 200; all readiness checks `ok`; route 200 in 1.4 s |
| CORS (dev server) | preflight from `localhost:3000` / `localhost:8080` / foreign origin | allowed / allowed / rejected (400) |

The 2 warnings: a deprecation warning from the test client library, and a short-key
warning from a test that deliberately forges a JWT.

### Reproducibility of the documented setup

| Step (README) | How tested | Outcome |
|---|---|---|
| `infrastructure/osrm/prepare_graphs.sh` | fresh run into an empty scratch folder (fresh Geofabrik download) | exit 0 in 14 min; car/foot/bicycle graphs built (1.1 GB / 426 MB / 434 MB); reproduced car graph routes Airport → Whitefield 38.3 km (existing graph 38.03 km; newer OSM data) |
| Gazetteer load (`docker compose run … geocoding.gazetteer`) | exact README command against a temporary database | 68,761 places loaded in 94 s |
| Admin bootstrap (`auth.bootstrap`) | against the same temporary database (password via environment variable) | administrator created; temporary database dropped afterwards |
| `docker compose up -d --build` from a fresh clone | **not tested** (would conflict with the running stack's ports); the same Dockerfiles/compose file built and ran in this workspace | — |

### Known failures / not verified

* No failing tests at the time of this run.
* Not verified: permanent public deployment, the native mobile app on a device or
  emulator, a full fresh-clone `docker compose up` on a second machine,
  load/performance beyond single-user latency. CI on GitHub covers commit `6b37482`
  only; later local commits have not been through GitHub CI.

## Automated suites

| Suite | Command | Result |
|---|---|---|
| Backend (unit + live integration) | `cd backend && python -m pytest -q` | **104 passed**, 0 failed, 0 skipped (219.8 s); re-run in the release audit: 104 passed, then **115 passed** after its additions (see RELEASE_READINESS.md) |
| Frontend | `CI=true npx react-scripts test --watchAll=false` | **7 passed** |
| Frontend production build | `CI=true npm run build` (lint warnings = errors) | compiled; 221.9 kB JS gz, 9.2 kB CSS |
| Mobile typecheck | `npx tsc --noEmit` | 0 errors |
| Mobile config | `npx expo-doctor` | 20/20 checks passed |
| Mobile JS bundles | `npx expo export --platform android --platform ios` | Android 638 modules, iOS 640 modules (Hermes, 1.7 MB each) |
| Mobile native build | `npx expo prebuild -p android && ./gradlew assembleDebug` | **app-debug.apk built** (150.6 MB, debug, all ABIs) |
| Migrations | fresh PostGIS DB: upgrade → check → downgrade → upgrade | pass; `alembic check`: no drift |

Backend tests by area (115 total): API surface 12, auth/RBAC 14, classification 8,
community 9, routing engine 15, offline forecasting pipeline 6, prospective forecast
logging 8, geometry/scoring 9, providers/ingestion/collector 15, live integration
4 test functions = 8 cases (5 benchmarks, modes, avoid-toll, migrations).

Forecasting tests use **synthetic test fixtures** to check the machinery (splits,
no lookahead, baselines, registry, activation gate, prediction-vs-actual matching).
They are not experimental evidence and no metric from them is reported as a result.

## Live integration (real OSRM graphs, PostGIS)

| Check | Result |
|---|---|
| 5 benchmark trips (Whitefield–Marathahalli, Whitefield–E‑City, Indiranagar–Yeshwanthpur, Airport–Whitefield, Koramangala–Hebbal) | all pass: distance bounds, steps, geometry, valid classes, no near-duplicates |
| Modes use distinct graphs | walk 3–6.5 km/h, bicycle 8–25 km/h, car > 25 km/h (measured 5.0 / 14.1 / 51 km/h free-flow) |
| `avoid=toll` | NICE Road present without, absent with avoid |
| TomTom live timing | Whitefield→E‑City: 5 routes on `traffic_live`; shortcut 21.4 km/66 min vs reference 24.7 km/77 min |
| Collector | each sweep: 26 flow stored, 6 weather stored, 300–350 incidents upserted |

## End-to-end workflow (browser, http://localhost:8080, production nginx build)

Open site → register (UI) → sign in → search "Koramangala" (suggestions) →
"Hebbal" → Find routes → 5 routes compared on TomTom live traffic, recommended
route drawn with incidents, explanation lists TomTom delay (9.1 min), typical
time (58.2 min), geometry match 99 %, monitored points, weather →
coordinates input ("12.9352, 77.6245") parsed → future departure (+1 h) →
TomTom reconstruction mismatch correctly rejected, comparison fell back to
free-flow with a warning → trip saved and listed in history → admin sign-in →
system health (all ok, TomTom 131/2000 calls), models & metrics (research
model listed as *candidate* with measured MAEs) → traffic page at 375 px width
(no horizontal page scroll).

## Security checks (live)

| Check | Result |
|---|---|
| Signed-in user → `GET /v1/admin/users` | 403 `forbidden` |
| Anonymous → admin API | 401 |
| User → `PATCH /v1/admin/users/1 {"role":"user"}` | 403 |
| User navigates to `#/admin` | UI falls back to Navigate |
| Registration with `"role":"admin"` | created as `user` (unit test) |
| Revoked / expired / forged JWT | 401 (unit tests) |
| Login brute force | 429 after 5 failures (unit test) |
| Other user's trip/favourite | 404 (unit test) |
| TomTom key in logs with an invalid key | 0 occurrences |

## Failure injection (live)

| Fault | Observed behaviour |
|---|---|
| Car OSRM stopped | `/health/ready` 503 with `osrm_car: down`, foot/bicycle ok; car route 503 `routing_engine_unavailable` in 0.26 s; walking route 200 |
| Car OSRM restarted | car routing 200 again after graph load |
| TomTom rejecting the key (HTTP 401) | routes 200 on `free_flow` basis, per-route note, preference `least_traffic_now` → `fastest` with explanation, source marked unavailable |
| Postgres + backend restarted | users, trips, 130 observations, 68,761 places unchanged |
| Collector restarted | resumed schedule, no immediate re-poll |

## Defects found by testing and fixed

1. **TomTom API key leaked in error responses** (V1) — safe provider errors + log redaction.
2. Dashboard endpoints served **random data** — removed (410) or backed by collected data.
3. Walking/cycling silently used the **car graph** — dedicated graphs, no fallback.
4. 1 s per HTTP client from CA-bundle loading (routes took 14–21 s) — shared SSL context (2–3 s).
5. `localhost` → IPv6 made psycopg hang on Windows — use `127.0.0.1` + connect timeout.
6. Duplicate check missed same-session rows (`autoflush=False`) — explicit flush.
7. Naive vs aware datetimes from SQLite — normalised to UTC.
8. Incidents on crossing side-streets attributed to routes — overlap-based matching.
9. Login rejected reserved-domain e-mails (bootstrap admin locked out) — login accepts any stored address.
10. A dead OSRM server starved uvloop's DNS threads so healthy servers looked down — circuit breaker + larger thread pool.
11. cp1252-encoded source written by a patch script — repaired; UTF-8 enforced.
12. Gazetteer bulk load 8 min — PostgreSQL COPY (5 s).
13. TomTom HTTP 401 (invalid key) did not stop a collector sweep (26 wasted calls per sweep) — now stops and backs off (release audit).
14. Collector could not write models/reports (read-only dirs) and the API could not see collector-trained models (unshared volume) — fixed and verified live (release audit).
15. Local web dev server (`npm start`, port 3000) blocked by CORS against the Docker backend — compose default now allows it; verified by preflight (R4 audit).

## Not verified

* GitHub Actions runs (not pushed); public deployment (no hosting account).
* Mobile app on a physical device or emulator (no AVD configured; APK built only).
* Load/performance testing beyond single-user latency.

## External access and mobile configuration (22 Oct 2026, 09:40–10:00 UTC)

| Check | Exact outcome |
|---|---|
| Docker services | 7 up; backend, OSRM ×3, Postgres healthy; collector 0 restarts |
| Local web/API | `localhost:8080` 200; `/api/health/ready` all `ok` |
| LAN binding | `http://192.168.1.7:8080` and `/api/health` → 200 from the laptop; 8000, 5433, 5000 on the LAN address refused (bound to 127.0.0.1) |
| Cloudflare quick tunnel | `cloudflared` 2026.10.3 (already installed, not on PATH) connected via `bom09` |
| Through the public HTTPS URL | page 200; readiness all `ok`; search "phoenix market" → Phoenix Market City; car route Koramangala → Hebbal on `traffic_live`, 3 routes; `GET /api/v1/admin/users` without token → 401 |
| Frontend → backend via tunnel (browser) | Traffic page issued 4 API calls, all 200; rendered 26/26 points fresh, 338 incidents |
| Mobile TypeScript | `npx tsc --noEmit` → 0 errors |
| Expo diagnostics | `npx expo-doctor` → 20/20 checks passed |
| Mobile iOS bundle | `npx expo export --platform ios` with the tunnel URL → bundled 640 modules; URL present once; 0 of 5 backend secrets present |
| Expo dev server (`--lan`) | manifest for iOS: `exposdk:58.0.0`, `hostUri 192.168.1.7:8081` |
| iPhone Safari → public HTTPS tunnel URL | **PASS — verified manually by the project owner** (page opened) |
| iPhone Safari → LAN URL `http://192.168.1.7:8080` (same Wi-Fi) | **PASS — verified manually by the project owner** (page opened) |
| iPhone Safari → route planning | **PASS — verified manually by the project owner** (a route was displayed) |
| Native Expo app on the physical iPhone | **not tested** — App Store Expo Go does not yet support SDK 58; a development build needs Apple signing (owner approval) |

Mobile-web success on the iPhone shows the deployed web app works on the phone; it does
**not** show that the native Expo app installs or launches on iOS.
