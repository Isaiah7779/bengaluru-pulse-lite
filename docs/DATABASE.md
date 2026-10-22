# Database

PostgreSQL 16 + PostGIS 3.4 (`postgis/postgis:16-3.4`) in all deployed
environments; SQLite only for unit tests and zero-dependency development.
ORM: SQLAlchemy 2 (`backend/db/models.py`). Migrations: Alembic (`backend/migrations/`).

## Tables

| Table | Purpose | Owner / privacy |
|---|---|---|
| users | accounts (email, bcrypt hash, role user/admin, active) | personal |
| revoked_tokens | logged-out JWT ids until expiry | security |
| audit_log | admin and security-relevant actions | ops |
| favourite_places | user's saved places | personal, user-deletable |
| trips | route searches the user chose to save (metrics summary, no GPS trace) | personal, user-deletable, 180-day retention |
| traffic_segments | monitored points + latest provider geometry/road class | public data |
| traffic_observations | flow observations (unique per segment/minute/source) | provider data (private research use) |
| weather_observations | Open-Meteo observations (unique per area/minute/source) | public data |
| incidents | TomTom + community incidents (unique per source/external id) | community reports moderated |
| provider_calls | every quota-limited call (budget + freshness) | ops, 90-day retention |
| places | OSM gazetteer (68,761 rows) | ODbL |
| route_submissions | community GPS traces + validation results | personal; raw trace purged after 90 days |
| shortcut_candidates | shortcut lifecycle (candidate → under_review → verified/rejected/stale) | derived |
| model_versions / evaluation_records / prediction_records | ML registry and metrics | research |
| legacy_predictions | V1 `/predict` history | legacy |

## Spatial and time indexes

Migration `0001` adds on PostgreSQL only:

* `geog geography(Point,4326)` **generated** columns (from lat/lon) with GiST indexes
  on traffic_segments, weather_observations, incidents, places, favourite_places,
  shortcut_candidates (origin).
* `pg_trgm` GIN index on `places.name_normalized` for fuzzy place search.
* B-tree indexes on all timestamp columns used for range queries
  (observed_at, last_seen_at, created_at, called_at, submitted_at) and on
  (segment_id, observed_at).

Migration `0002` adds `evaluation_records.candidate`.

Verified: `upgrade head → check → downgrade base → upgrade head` on a fresh PostGIS
database (`tests/test_integration_live.py::test_alembic_migrations_on_fresh_postgis_database`);
`alembic check` reports no drift between models and schema.

## Retention and privacy (daily job, `traffic/maintenance.py`)

| Data | Retention |
|---|---|
| traffic/weather observations | 730 days (`RETENTION_OBSERVATION_DAYS`) |
| trips | 180 days (`RETENTION_TRIP_DAYS`) |
| raw GPS traces in submissions | 90 days (`RETENTION_SUBMISSION_TRACE_DAYS`); matched geometry kept |
| revoked tokens | until token expiry |
| provider call log | 90 days |

Users can delete individual trips, all trips, favourites, or their whole account
(`POST /v1/auth/me/delete`, cascades to personal rows). Every query for personal
data is filtered by the authenticated user id.

## Persistence

Data lives in the named volume `bp_pgdata`. Verified: user, trip, observation and
place counts were identical before and after `docker compose restart postgres backend`.
Backups (recommended for the VM): `docker compose exec postgres pg_dump -U pulse -Fc pulse > backup.dump`
on a cron schedule; restore with `pg_restore`.

## Rebuilding the gazetteer

```bash
docker compose exec backend python -m geocoding.gazetteer /path/in/container/bengaluru.osm.pbf
```
Uses PostgreSQL `COPY` (68,761 places loaded in ~5 s after a ~35 s extraction).
