# Deployment

## Local Docker deployment

1. Install Docker Desktop and ensure it is running.
2. Copy `.env.example` to `.env`. Add `TOMTOM_API_KEY` only when live traffic
   is required.
3. Start the full routing stack:

   ```powershell
   docker compose --profile routing up --build
   ```

4. Open `http://localhost:8080`. The API health endpoint is
   `http://localhost:8000/health`.

The OSRM container mounts `data/osrm` read-only and runs the existing
`bengaluru.osrm` MLD graph. It does not regenerate the graph on startup.

## Degraded operation

`docker compose up --build` starts the dashboard and API without OSRM. Traffic
prediction remains available; routing returns a clear upstream error until
OSRM is started. Omitting TomTom only disables route-specific live ETA.

## Production notes

- Terminate TLS at a managed load balancer or reverse proxy and set an explicit
  production `CORS_ORIGINS` value.
- Store `TOMTOM_API_KEY` in a secret manager, not in `.env` committed to Git.
- Back up the `traffic_data` volume before deploying a replacement stack.
- Use a managed Postgres/PostGIS migration before scaling history or spatial
  traffic observations beyond this legacy SQLite baseline.
