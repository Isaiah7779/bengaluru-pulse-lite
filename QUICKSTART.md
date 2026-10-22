# Quick start

## Prerequisites

* Docker Desktop (≈ 4 GB RAM for the VM is enough; ≈ 3 GB disk for graphs and images)
* Optional for development without Docker: Python 3.12, Node 22

## 1. Routing graphs (one time)

If `data/osm/bengaluru.osrm.*`, `data/osrm-foot/` and `data/osrm-bicycle/` already
exist, skip this. Otherwise (≈ 10 minutes, ≈ 2 GB):

```bash
bash infrastructure/osrm/prepare_graphs.sh "$(pwd)/data"
```

## 2. Configuration

```bash
cp .env.example .env
cp backend/.env.example backend/.env    # add TOMTOM_API_KEY for live traffic (optional)
```

Without a TomTom key the app still routes, using OSRM free-flow times (labelled as such).

## 3. Start everything

```bash
docker compose up -d --build
docker compose run --rm -v "$(pwd)/data/osm:/data:ro" backend python -m geocoding.gazetteer /data/bengaluru.osm.pbf
docker compose exec backend python -m auth.bootstrap --email you@example.org --name "Your Name"
```

* Web app: http://localhost:8080
* API docs: http://localhost:8000/docs
* Readiness (DB, OSRM ×3, TomTom budget, data freshness): http://localhost:8000/health/ready

The `collector` service starts gathering TomTom flow/incidents and Open-Meteo weather
immediately and runs the daily retention job and retraining attempt.

## Tests

```bash
cd backend && python -m pytest -q          # unit + live integration (skips if services are down)
cd frontend && CI=true npm test -- --watchAll=false && npm run build
cd mobile && npx tsc --noEmit && npx expo export --platform android
```

## Mobile app

```bash
cd mobile
echo "EXPO_PUBLIC_API_BASE_URL=http://<your-LAN-IP>:8000" > .env
npx expo start            # open in Expo Go, or: npx expo run:android
```

## Development without Docker

Run PostGIS and OSRM in Docker, the API with `uvicorn main:app --reload` from
`backend/` (settings from `backend/.env`; use `127.0.0.1`, not `localhost`, for
Postgres on Windows), and the web app with `npm start` in `frontend/`.
