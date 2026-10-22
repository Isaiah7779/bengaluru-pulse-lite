# Traffic, weather and incident data

## Sources

| Data | Provider | Endpoint | Frequency | Coverage |
|---|---|---|---|---|
| Flow (speed vs free-flow) | TomTom Traffic Flow Segment v4 | `flowSegmentData/absolute/10` | every 30 min | **26 monitored sample points** on major corridors (`traffic/segments.py`) |
| Incidents | TomTom Traffic Incident Details v5 | `incidentDetails` (bbox 77.35–77.90, 12.75–13.26) | hourly | whole metro bbox |
| Route timing | TomTom Routing v1 | `calculateRoute` (POST, supportingPoints) | per route request | per route |
| Weather | Open-Meteo | `/v1/forecast` current + hourly | every 30 min | 6 area points (central/east/north/south/west/airport) |
| Community incidents | users | `POST /v1/incidents/report` | on demand | pending until an admin publishes |

**Coverage statement.** Flow observations exist only at the 26 monitored points.
They are *samples*, not city-wide coverage; the UI and API say so
(`coverage_note`). Some points snap to minor roads (e.g. the Bannerghatta Road
point resolved to an FRC5 road in the first sweep) — the returned road class and
geometry are stored and visible to admins.

## Quota budget (TomTom free tier: 2,500 non-tile requests/day, verified 2026‑10‑22)

* `TOMTOM_DAILY_BUDGET=2000` hard cap enforced in the database (`provider_calls`),
  shared by all processes; `background_reserve=500` keeps calls for users —
  the collector stops when only the reserve remains.
* Collector: 26 × 48 flow sweeps (1,248) + 24 incident sweeps ≈ 1,272/day.
* Routing: ≤ 5 timings per request, cached 5 minutes.
* After restarts the collector resumes its previous schedule instead of polling
  immediately (each flow sweep costs 26 calls).
* Measured on the first day (2026‑10‑22, partial): 188 TomTom calls by ~05:35 UTC.

## Ingestion pipeline

1. **Validate** (`providers/tomtom.parse_flow` etc.): speeds 0–200 km/h,
   free-flow > 0, zero current speed only with a road closure, confidence in [0,1];
   incidents need an id and a location; Open-Meteo temperature −10…55 °C.
   Invalid readings are counted and skipped, never stored.
2. **Normalise**: timestamps to UTC minute buckets; speed ratio capped at 1.5.
3. **De-duplicate**: unique (segment, minute, source) and (area, minute, source);
   incidents upsert on (source, external_id).
4. **Staleness**: observations older than 90 min are reported as `stale`;
   incidents absent from the latest sweep are deactivated.
5. **Failure handling**: each task is isolated; failures back off exponentially
   (×2 … ×8 interval); quota exhaustion stops background polling cleanly.

## Read APIs

* `GET /v1/traffic/segments` — latest observation per point with status fresh/stale/no_data.
* `GET /v1/traffic/segments/{id}/history?hours=` — collected time series.
* `GET /v1/incidents` — active published incidents (TomTom + moderated community).
* `GET /v1/weather/current`, `/v1/weather/at?when=`, `/v1/weather/areas`.
* Legacy `GET /hotspots`, `/incidents`, `/api/live-traffic/bengaluru` now serve the
  same collected data (previously simulated).

## Data collected so far (measured 2026‑10‑22 05:35 UTC)

| Table | Rows | Period |
|---|---|---|
| traffic_observations | 156 | 03:16 – 05:35 UTC (first day) |
| weather_observations | 36 | same |
| incidents | 632 seen, 358 active | same |

Collection continues while the `collector` container runs. Forecasting on these
observations requires ≥ 14 days (see ML_PIPELINE.md).

## Terms and attribution

* **TomTom:** used within the free developer tier. I could not locate an explicit
  clause on storing API responses; collected observations are therefore kept as
  private research data and are not redistributed. The owner should confirm the
  applicable TomTom terms before publishing any dataset derived from them.
* **Open-Meteo:** CC BY 4.0; attribution shown wherever weather appears.
* **OpenStreetMap:** ODbL; attribution on every map and search result.
