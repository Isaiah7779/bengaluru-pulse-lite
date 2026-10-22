# Test report

All results below were produced on 2026‑10‑22 on the development machine
(Windows 11, 8 CPUs, 14.8 GB RAM, Docker Desktop 29.7, Python 3.12, Node 22.18)
with the local Docker Compose stack running. Nothing here was run on GitHub
Actions (the branch is not pushed).

## Automated suites

| Suite | Command | Result |
|---|---|---|
| Backend (unit + live integration) | `cd backend && python -m pytest -q` | **104 passed**, 0 failed, 0 skipped (219.8 s) |
| Frontend | `CI=true npx react-scripts test --watchAll=false` | **7 passed** |
| Frontend production build | `CI=true npm run build` (lint warnings = errors) | compiled; 221.9 kB JS gz, 9.2 kB CSS |
| Mobile typecheck | `npx tsc --noEmit` | 0 errors |
| Mobile config | `npx expo-doctor` | 20/20 checks passed |
| Mobile JS bundles | `npx expo export --platform android --platform ios` | Android 638 modules, iOS 640 modules (Hermes, 1.7 MB each) |
| Mobile native build | `npx expo prebuild -p android && ./gradlew assembleDebug` | **app-debug.apk built** (150.6 MB, debug, all ABIs) |
| Migrations | fresh PostGIS DB: upgrade → check → downgrade → upgrade | pass; `alembic check`: no drift |

Backend tests by area: API surface 12, auth/RBAC 14, classification 8, community 9,
routing engine 15, forecasting 6, geometry/scoring 9, providers/ingestion 12,
live integration 4 test functions = 8 cases (5 benchmarks, modes, avoid-toll, migrations).

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

## Not verified

* GitHub Actions runs (not pushed); public deployment (no hosting account).
* Mobile app on a physical device or emulator (no AVD configured; APK built only).
* Load/performance testing beyond single-user latency.
