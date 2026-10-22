# Bengaluru Pulse

Route planning for Bengaluru that explains itself. Bengaluru Pulse compares several
real road routes across the full city OpenStreetMap graph, times them with live or
predicted traffic where available, flags genuine **shortcuts** (shorter *and* faster)
and **longcuts** (longer but faster), and shows exactly where every number came from.
Nothing is simulated: when a data source is missing, the app says so.

* **Web**: map-centred navigation, traffic, account and admin pages (React).
* **Mobile**: Expo / React Native app on the same API.
* **API**: FastAPI + PostgreSQL/PostGIS + OSRM (car, foot, bicycle graphs).

## What it does

| Feature | Data behind it |
|---|---|
| Place search (addresses, landmarks, shops, localities, coordinates, GPS, map tap) | 68,761-place OpenStreetMap gazetteer; Photon fallback |
| Car, motorcycle, bicycle and walking routes | OSRM car / foot / bicycle graphs (motorcycle on the car graph, disclosed) |
| Up to 5 diverse alternatives with turn-by-turn steps | OSRM + corridor candidates, geometric dedup |
| Live and future-departure travel times | TomTom routing on each route's own geometry (length-verified) |
| Fastest / shortest / least traffic / balanced; avoid tolls, expressways, ferries | documented scoring |
| Shortcut / longcut labels against an explicit reference route | strict definitions, same time basis |
| Incidents, monitored traffic points, weather | TomTom incidents & flow (collected), Open-Meteo |
| Forecasts | only from a model that beat baselines on held-out data — none yet (see below) |
| Community shortcuts | GPS trips → map matching → 3 independent confirmations → admin review |
| Accounts | trip history, favourites, incident reports; admin moderation, data freshness, model metrics, health |

## Honest status

* Runs end-to-end locally (Docker Compose); **not yet publicly deployed** — needs an
  owner-created hosting account (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).
* Forecasting: on the public daily dataset no model beats the historical average;
  the operational forecaster waits for ≥ 14 days of collected data
  ([docs/ML_PIPELINE.md](docs/ML_PIPELINE.md)).
* Traffic flow is observed at 26 sample points, not city-wide.

## Quick start

See [QUICKSTART.md](QUICKSTART.md). In short:

```bash
docker compose up -d --build
```
then open http://localhost:8080.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Routing](docs/ROUTING.md) · [Traffic](docs/TRAFFIC.md) ·
[ML pipeline](docs/ML_PIPELINE.md) · [Database](docs/DATABASE.md) · [Security](docs/SECURITY.md) ·
[Tests](docs/TEST_REPORT.md) · [Deployment](docs/DEPLOYMENT.md) · [Research](docs/RESEARCH.md) ·
[Status](docs/PROJECT_STATUS.md) · [Final audit](docs/FINAL_SYSTEM_AUDIT.md)

## Data and attribution

Map data © OpenStreetMap contributors (ODbL). Weather by Open-Meteo.com (CC BY 4.0).
Traffic by TomTom (free developer tier). Geocoding fallback by Photon (komoot).
