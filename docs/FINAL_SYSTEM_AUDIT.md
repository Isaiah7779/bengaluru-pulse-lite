# Final system audit — 2026‑10‑22

Legend: **Implemented** = code exists · **Tested** = automated tests pass ·
**Verified live** = exercised against real local services/browser ·
**Deployed** = publicly reachable · **Externally verified** = confirmed by a third party/environment outside this machine.

| Requirement | Implemented | Tested | Verified live | Deployed | Externally verified |
|---|---|---|---|---|---|
| Full Bengaluru OSM graph routing (OSRM MLD) | ✅ | ✅ | ✅ 5 benchmarks | ❌ | ❌ |
| Diverse candidates + geometry-aware dedup | ✅ | ✅ | ✅ | ❌ | ❌ |
| Car / bicycle / walking on genuine profiles | ✅ | ✅ | ✅ | ❌ | ❌ |
| Motorcycle | ✅ car-graph approximation (disclosed) | ✅ | ✅ | ❌ | ❌ |
| Geocoding: addresses, landmarks, shops, localities, coordinates, GPS, map pick | ✅ | ✅ | ✅ browser | ❌ | ❌ |
| TomTom current traffic (flow, incidents, route timing) | ✅ | ✅ | ✅ | ❌ | ✅ TomTom API responses |
| Open-Meteo weather | ✅ | ✅ | ✅ | ❌ | ✅ Open-Meteo responses |
| Automatic historical collection | ✅ | ✅ | ✅ running in Docker | ❌ | ❌ |
| PostgreSQL/PostGIS persistence + migrations | ✅ | ✅ | ✅ restart persistence | ❌ | ❌ |
| Forecasting pipeline with chronological evaluation | ✅ | ✅ | ✅ research run | ❌ | ❌ |
| Forecast-aware routing | ✅ TomTom departAt; Pulse model gated | ✅ | ✅ (provider prediction) | ❌ | ❌ |
| **Accurate Pulse forecasts** | ❌ no model beats baselines yet | — | — | — | — |
| Shortcut / longcut detection | ✅ | ✅ exhaustive | ✅ live shortcut seen | ❌ | ❌ |
| Community submissions + verification lifecycle | ✅ | ✅ | ◐ API only, no real submissions | ❌ | ❌ |
| Auth, User/Admin RBAC, admin bootstrap | ✅ | ✅ | ✅ | ❌ | ❌ |
| Web app (navigate, traffic, account, admin) | ✅ | ✅ | ✅ browser walkthrough | ❌ | ❌ |
| Mobile app (Expo) | ✅ | ✅ typecheck/bundle/APK build | ❌ not run on device | ❌ | ❌ |
| Docker / Compose / health checks | ✅ | ✅ | ✅ | ❌ | ❌ |
| HTTPS, prod CORS, single-VM deployment | ✅ prepared (Caddy overlay) | ✅ config renders | ❌ | ❌ | ❌ |
| CI/CD | ✅ workflows written | ✅ commands run locally | ❌ not run on GitHub | ❌ | ❌ |

## Hard-rule compliance

* No fabricated data in product paths: simulated forecast/hotspot/trend/incident
  endpoints removed; synthetic series exist only as labelled test fixtures.
* No accuracy claims without evaluation: the only accuracy numbers are measured,
  chronological, and show no model beats the baseline.
* No deployment URL claimed. No purchases, accounts or billable resources created.
* Secrets: none committed; key redaction verified.

## Outstanding limitations

1. Public deployment requires the owner's Oracle Cloud (or similar) account — see DEPLOYMENT.md.
2. Branch `v2-build` is local; pushing to the public GitHub repo awaits the owner.
3. Forecasting on collected data needs ≥ 14 days of observations (from 2026‑10‑22).
4. Traffic flow covers 26 sample points, not the whole city.
5. Mobile app not exercised on a device; iOS not built (requires macOS).
6. No e-mail verification/password reset; in-process login rate limiter; no CSP yet.
7. TomTom data-storage terms to be confirmed before publishing collected data.

## Side effects on this machine

* Docker containers `bengalurupulselite-*` running (collector uses ~1,300 TomTom calls/day).
* Android SDK: Gradle auto-installed Build-Tools 37, Platform 37, CMake 3.22.1 and NDK 27.1 (licenses auto-accepted).
* `backend/.env` appended with local settings and dev credentials (backup in `data/.env.backup-20261022`).
* Local branch `v2-build` with 7 commits on top of `main`.

## Actual cost: ₹0
