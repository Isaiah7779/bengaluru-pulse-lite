# Bengaluru Pulse V2

Evidence-based route planning and traffic intelligence for Bengaluru.

Bengaluru Pulse compares several real routes across the full OpenStreetMap road
network for **car, motorcycle, bicycle and walking**. It times car and motorcycle
routes with live or predicted **TomTom** traffic, labels **shortcuts** (shorter *and*
faster) and **longcuts** (longer but faster) against a stated reference route, and
shows where every number came from. When a data source is unavailable the app says
so; nothing is simulated.

> Project status (Oct 2026): runs end-to-end locally with Docker. **Not publicly
> deployed. No forecasting model has been validated yet**; see
> [docs/RESULTS_AND_LIMITATIONS.md](docs/RESULTS_AND_LIMITATIONS.md).

## Features

| Feature | Backed by |
|---|---|
| Place search: addresses, landmarks, shops, localities, coordinates, GPS, map tap | 68,761-place OSM gazetteer (Photon fallback) |
| Car / motorcycle / bicycle / walking routes with turn-by-turn steps | OSRM car, foot and bicycle graphs (motorcycle uses the car graph, disclosed) |
| Up to 5 diverse alternatives | OSRM alternatives + corridor candidates, geometric deduplication |
| Live or future-departure travel times | TomTom routing on each route's own geometry |
| Preferences: fastest, shortest, least traffic now/predicted, balanced; avoid tolls/expressways/ferries | documented scoring |
| Shortcut / longcut labels | strict definitions, same time basis |
| Incidents, monitored traffic points, weather | collected from TomTom and Open-Meteo |
| Accounts: trip history, favourites, incident reports, community route sharing | PostgreSQL/PostGIS |
| Admin: health, data freshness, moderation, model metrics, users, audit log | role checked in the backend |
| Mobile app | Expo / React Native on the same API |

## Supported platforms

One backend API serves every client.

| Platform | Use | Status |
|---|---|---|
| Any modern browser (Windows, macOS, Linux, Android, iPhone, iPad) | open the web app URL | responsive phone/tablet/desktop layouts; verified in Chromium and on an iPhone (Safari) |
| Android | install the APK, then *Account → Server* | release APK built and verified; not yet installed on a device |
| iPhone/iPad app | development/ad hoc build | prepared; needs a paid Apple Developer account (use Safari meanwhile) |

Details: [docs/DEPLOYMENT_GUIDE.md §10](docs/DEPLOYMENT_GUIDE.md#10-platform-support).

## Repository layout

```
backend/          FastAPI app, routing engine, collector, forecasting, tests
frontend/         React web app (served by nginx in Docker)
mobile/           Expo mobile app
infrastructure/   OSRM graph build scripts, Caddy config (production)
docs/             reports and guides (start with docs/FINAL_PROJECT_REPORT.md)
docker-compose.yml           local stack
docker-compose.prod.yml      production overlay (HTTPS, single server)
```

## Prerequisites

* Docker Desktop (Compose v2.24+). Allocate ≥ 4 GB RAM; ≈ 5 GB free disk for images, graphs and the OSM download.
* Git and a Bash shell (Git Bash on Windows) for the graph-build script.
* Internet access for the first build (Docker images, Geofabrik OSM extract).
* Optional: a free TomTom developer API key for live traffic; Python 3.12 and Node 22 for running tests outside Docker.

## Installation

From the submission ZIP: unzip it and open a terminal in the extracted folder.

From Git (the `v2-build` branch is on GitHub; the newest local commits may not be pushed yet):

```bash
git clone https://github.com/Isaiah7779/bengaluru-pulse-lite.git
cd bengaluru-pulse-lite
git checkout v2-build
```

### 1. Build the road graphs (one time, ≈ 10–20 min)

```bash
bash infrastructure/osrm/prepare_graphs.sh "$(pwd)/data"
```

This downloads the Geofabrik *India – Southern Zone* extract (~560 MB), cuts the
Bengaluru area and builds `data/osm/` (car), `data/osrm-foot/` and `data/osrm-bicycle/`.
Skip it if those folders already contain `bengaluru.osrm.*` files.

### 2. Environment setup

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

* `TOMTOM_API_KEY=` your key (optional; without it routes use OSRM free-flow times, clearly labelled).
* `JWT_SECRET=` a random string (`python -c "import secrets; print(secrets.token_urlsafe(48))"`); optional for local use.

A root `.env` is optional for local use (defaults are built in); copy `.env.example` only to change ports or the database password.
Never commit `.env` files (they are gitignored).

### 3. Start with Docker

```bash
docker compose up -d --build
```

Services: `postgres`, `osrm-car`, `osrm-foot`, `osrm-bicycle`, `backend`, `collector`, `frontend`.
The backend applies database migrations on start-up.

### 4. Load place search and create an administrator (one time)

```bash
docker compose run --rm -v "$(pwd)/data/osm:/data:ro" backend python -m geocoding.gazetteer /data/bengaluru.osm.pbf
docker compose exec backend python -m auth.bootstrap --email you@example.org --name "Your Name"
```

The bootstrap command prompts for a password (≥ 14 characters, mixed case and a digit).

## Usage

| What | Where |
|---|---|
| Web app | http://localhost:8080 |
| API documentation (Swagger) | http://localhost:8000/docs |
| Readiness of all dependencies | http://localhost:8000/health/ready |

Plan a route: type a start and destination (or use ◎ for GPS / ⌖ to tap the map),
choose a travel mode, preference and departure, then **Find routes**. Click any
route card to see its explanation, incidents and steps. Sign in to save trips,
report incidents or share a route; sign in as an administrator for the Admin page.
Step-by-step guide: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Tests

```bash
cd backend && python -m pip install -r requirements-dev.txt && python -m pytest -q
cd frontend && npm ci && CI=true npm test -- --watchAll=false && npm run build
cd mobile && npm ci && npx tsc --noEmit
```

Backend integration tests use the running Docker services (OSRM on ports
5000–5002, PostGIS on 5433) and skip automatically if they are not running.
Results: [docs/TEST_REPORT.md](docs/TEST_REPORT.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/health/ready` shows an OSRM service `down` | `docker compose ps`; check the graph folders exist; `docker compose logs osrm-car`. A routing server recovers ~20 s after restart. |
| Routes show "Free-flow estimate" only | No or invalid `TOMTOM_API_KEY`, or the daily budget is used up (Admin → System health shows usage). |
| Place search finds nothing | The gazetteer was not loaded; run step 4. |
| "Cannot reach the Bengaluru Pulse server" in the browser | Backend not healthy: `docker compose logs backend`. |
| Port already in use (5000–5002, 5433, 8000, 8080) | Stop the conflicting program, or set `FRONTEND_PORT` / `POSTGRES_HOST_PORT` in a root `.env`. |
| Python cannot connect to Postgres on Windows | Use `127.0.0.1`, not `localhost`, in `DATABASE_URL`. |
| Web app via `npm start` blocked by CORS | Use the default compose settings (allow `localhost:3000`) or set `CORS_ORIGINS`. |

## Shutdown

```bash
docker compose stop          # stop everything, keep data
docker compose down          # remove containers, keep data volumes
```

Data (database, collected observations, models) lives in Docker volumes and
survives both commands. **`docker compose down -v` deletes all collected data**;
don't use it unless you intend to.

## Documentation

* Report: [FINAL_PROJECT_REPORT](docs/FINAL_PROJECT_REPORT.md) · [RESULTS_AND_LIMITATIONS](docs/RESULTS_AND_LIMITATIONS.md) · [TEST_REPORT](docs/TEST_REPORT.md)
* Guides: [USER_GUIDE](docs/USER_GUIDE.md) · [DEPLOYMENT_GUIDE](docs/DEPLOYMENT_GUIDE.md) · [QUICKSTART](QUICKSTART.md)
* Review: [DEMO_SCRIPT](docs/DEMO_SCRIPT.md) · [PRESENTATION_OUTLINE](docs/PRESENTATION_OUTLINE.md) · [SUBMISSION_CHECKLIST](docs/SUBMISSION_CHECKLIST.md)
* Design: [ARCHITECTURE](docs/ARCHITECTURE.md) · [ROUTING](docs/ROUTING.md) · [TRAFFIC](docs/TRAFFIC.md) · [ML_PIPELINE](docs/ML_PIPELINE.md) · [DATABASE](docs/DATABASE.md) · [SECURITY](docs/SECURITY.md)

## Data and attribution

Map data © OpenStreetMap contributors (ODbL). Weather by Open-Meteo.com (CC BY 4.0).
Traffic by TomTom (free developer tier). Geocoding fallback by Photon (komoot).
