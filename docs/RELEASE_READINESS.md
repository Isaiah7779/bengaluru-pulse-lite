# Release readiness audit — 2026‑10‑22

Scope: branch `v2-build` (commits `2e42577` … `a0ad6f8` plus this audit's commit),
local Docker stack, Android debug build. Every finding below was checked by
running a command during this audit; nothing was pushed, published, deleted or rotated.

## Verdict

**Ready for a private/local release. Not ready for public release** until the
owner resolves the blockers in §9 (hosting account, TomTom terms, push decision,
secret handling on OneDrive).

## 1. Test results (re-run)

| Suite | Reported earlier | Re-run now |
|---|---|---|
| Backend (unit + live integration, live OSRM/PostGIS) | 104 passed | **104 passed** before fixes (76 s); **115 passed** after this audit's additions (113 s), 0 skipped |
| Frontend | 7 passed | **7 passed** |

The 11 new tests: 3 collector-failure tests, 8 prospective-forecasting tests.
The only warning is a deliberately forged short-key JWT in an auth test.

## 2. Commits and diff (161 files, +20,289 / −13,250 vs `main`)

| Check | Finding |
|---|---|
| Secret values (TomTom key, JWT secret, dev passwords, MEM_BRAIN key) in tracked files | **none** (`git grep -F` on actual values) |
| …in git history (`git log --all -S`) | **none** |
| …in container logs (backend, collector, frontend) | **0 occurrences** |
| Secret-like assignments in the diff | none (only placeholders/test fixtures) |
| Tracked `.env` files | only `*.env.example` templates |
| Local dev credentials | only as comments in gitignored `backend/.env`; docs reference the location, not values |
| Personal data | none; all e-mails in tracked files are fixtures on `example.com/.org` or `.test` |
| Collected traffic data | not tracked; `backend/evaluation/v2/*.json` contain counts and aggregate metrics only |
| Large/generated files | largest tracked: `frontend/package-lock.json` 689 kB, Expo template `icon.png` 393 kB; native `mobile/android` (2.3 GB), APK, OSRM graphs, `data/` all gitignored |
| Legacy runtime file | `backend/traffic.db` is tracked (since `main`): 12 legacy prediction rows, no personal data. Recommend untracking (needs your OK) |

## 3. Secret protection

* `backend/.env`, `data/.env.backup-20261022` and `mobile/.env` are gitignored (`git check-ignore` verified).
* **Risk (pre-existing, owner decision):** the project lives in `OneDrive\Desktop`, so
  `backend/.env` *and its backup* (real TomTom key, JWT secret, dev passwords) are
  synced to OneDrive. Options: move secrets out of the synced folder, exclude the
  files from sync, or delete the backup once no longer needed. Not changed without your approval.
* V1 code could return the TomTom key in API error responses. If any V1 build was
  ever reachable by others, consider rotating the key in the TomTom portal (your action).
* Error responses: provider errors return safe messages; verified live with an invalid key (no key in body or logs).
* Two scratch files with the local test passwords (outside the repo, session temp dir)
  were deleted during this audit. The dev passwords were entered in the local browser
  during testing; they protect only the local Docker database.

## 4. TomTom request rate and budget (measured from `provider_calls`)

| Hour (UTC) | Flow | Incidents | Route timing |
|---|---|---|---|
| 03:00 | 52 | 2 | 11 |
| 04:00 | 52 | 1 | 8 |
| 05:00 | 52 | 1 | 9 (2 = deliberate invalid-key test) |

* Steady state: **52 flow + 1 incident call per hour ≈ 1,272 calls/day**, under the
  enforced cap of 2,000 (500 reserved for users) and TomTom's 2,500 free calls/day.
  Today so far: 266 collector + 29 route-timing calls (07:59 UTC).
* Restarts: collector resumes its schedule — **0 calls** caused by the 3 restarts in this audit.
* Retries: none per request. Polling frequency was not changed.
* **Defect fixed:** HTTP 401 (invalid/revoked key) was treated as an ordinary error,
  so each sweep would have spent all 26 calls every 30 minutes. 401 now stops the
  sweep like 403; 3 consecutive errors abort a sweep; the scheduler backs off
  (×2 … ×8 interval) after an unavailable/aborted sweep. Tested.

## 5. Health, persistence, collection, routing, failure behaviour (live)

| Check | Result |
|---|---|
| `/health/ready` | ok: database, OSRM car/foot/bicycle, TomTom budget, traffic data |
| Persistence across rebuild/restart | users 2, trips 1, observations growing (260), places 68,761 unchanged |
| Scheduled collection | sweeps at 05:04, 05:35, 06:05, 07:3x; retention job ran 05:59 |
| Routing | car (traffic-timed) and bicycle routes 200 |
| Foot OSRM stopped | walk 503 (3.2 s first, then 0.23 s via circuit breaker); car 200; recovery 200 |
| TomTom failing (earlier today) | routes on free-flow with per-route notes; key absent from logs |
| **Defect fixed:** model/report persistence | the collector's `/app/models` and `/app/evaluation/v2` were **not writable** (files from the Windows build context arrived read-only), so the daily retrain would have crashed; and the models volume was mounted only on the backend, so the API could never load collector-trained models. Image now makes these dirs writable; both services share `models` and `evaluations` volumes; verified retrain-in-collector → report visible in backend; CI asserts writability |

## 6. Android build

* `mobile/android/app/build/outputs/apk/debug/app-debug.apk` (150.6 MB) is a **debug**
  build: native libraries for arm64‑v8a, armeabi‑v7a, x86, x86_64 but **no JavaScript
  bundle** — it loads JS from a Metro dev server (`npx expo start`). Cleartext HTTP is
  enabled only in debug variants.
* Built with `EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000` (the emulator's alias for the host).
* Installed SDK pieces: platform-tools (adb), system image *android‑35 google_apis_playstore x86_64*;
  **no AVD and no `cmdline-tools`/Android Studio**, so an emulator cannot be created yet.

**Safest test options (your choice; nothing installed or run on a device yet):**

1. **Emulator (recommended — nothing touches your phone):** install Android Studio (or
   SDK *cmdline-tools*), create an AVD from the existing android‑35 x86_64 image, start it,
   then from `mobile/`: `npx expo run:android` (builds, installs and starts Metro).
   The API is reached at `10.0.2.2:8000` without exposing it on your network.
2. **Physical phone over USB, without exposing the backend on Wi‑Fi:** enable Developer
   options → USB debugging; connect; then
   `adb reverse tcp:8000 tcp:8000` and `adb reverse tcp:8081 tcp:8081`, rebuild with
   `EXPO_PUBLIC_API_BASE_URL=http://localhost:8000`, `npx expo run:android`.
   Avoid binding the backend to `0.0.0.0` on an untrusted network.
3. Do not distribute the debug APK; a shareable build needs a release build signed
   with your own keystore (or EAS Build with your Expo account).

## 7. Data-source terms (checked 2026‑10‑22)

| Source | What I could verify | Publication recommendation |
|---|---|---|
| **TomTom** APIs (flow, incidents, routing) | Free tier 2,500 non-tile requests/day; FAQ says APIs may be used commercially. The legal terms page renders client-side and could not be read; the PDF found is the **SDK** licence (not the online-API terms) and does not cover storing traffic data. | **Do not publish raw collected observations or incidents** until you read the Terms & Conditions in your TomTom developer account or get written confirmation from TomTom. Aggregate error metrics in a thesis are lower risk but should be confirmed too. |
| **Open-Meteo** | Free API: non-commercial use only, < 10,000 calls/day, 5,000/h, 600/min; data CC BY 4.0 with attribution "Weather data by Open-Meteo.com". Our use: 12 calls/h. | Fine for the academic project with attribution; contact Open-Meteo before any commercial use. |
| **OpenStreetMap** | ODbL (attribution; share-alike for publicly used derivative databases); tile usage policy for tile.openstreetmap.org. | The gazetteer and OSRM graphs are ODbL derivatives — publish them only under ODbL with attribution. For a public site with real traffic, use a tile provider/plan meant for production rather than OSM's volunteer tile servers. |
| **Photon (komoot)** | "Fair use" public instance; no autocomplete ban found. | Keep as low-volume fallback only. |

## 8. Deployment options (no accounts created, nothing published)

Unchanged from DEPLOYMENT.md (constraints verified earlier today): the only verified
₹0 option that can host all three OSRM graphs, the API, PostGIS and HTTPS on one
machine is an **Oracle Cloud Always Free Ampere A1 VM** (reported 2 OCPU / 12 GB
since mid‑2026; card verification at sign-up; idle reclamation rules). Render/Koyeb
free tiers lack memory and disk for OSRM; Hugging Face Docker Spaces now need a paid
plan; Google's e2‑micro has 1 GB RAM. The production overlay (Caddy HTTPS, only
ports 80/443 exposed, production secrets mandatory) and a manual-only deploy
workflow are prepared and untested against a real host.

## 9. Blockers and exact next steps

| # | Blocker | Who | Next step |
|---|---|---|---|
| 1 | Secrets in an OneDrive-synced folder (+ backup copy) | you | Decide: move/exclude/delete `data/.env.backup-20261022`; consider moving `backend/.env` outside OneDrive |
| 2 | TomTom storage/publication terms unverified | you | Read the T&C in your TomTom developer account; until then keep observations private |
| 3 | Branch not pushed; CI never ran on GitHub | you | Say "push v2-build" — the repo is public, so the push publishes all code and docs |
| 4 | No public host | you | Create the Oracle account/VM, then follow DEPLOYMENT.md §3 |
| 5 | Mobile app never run | you | Choose emulator (option 1) or USB device (option 2) above |
| 6 | 2.3 GB generated `mobile/android` in OneDrive | you | Approve deleting it (re-creatable with `npx expo prebuild`) or exclude from sync |
| 7 | `backend/traffic.db` tracked | you | Approve `git rm --cached backend/traffic.db` (file stays on disk) |
| 8 | Forecasting unvalidated | time | Keep the collector running; follow RESEARCH_MILESTONE_FORECASTING.md (M2 ≈ 29 Oct, M3/M4 ≈ 5 Nov) |

## Changes made during this audit

* `a0ad6f8` — 401 handling, sweep abort/back-off, writable runtime dirs, shared volumes, CI writability check.
* This commit — prospective forecast logging (`forecasting/online.py`, collector hook,
  `GET /v1/admin/forecast/online`), 8 tests, this report, the research milestone plan.
