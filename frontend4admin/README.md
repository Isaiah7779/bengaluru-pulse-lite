# Bengaluru Pulse V2 Admin Intelligence Dashboard

This is a separate, read-only React dashboard. It uses the commuter app's React, Recharts, Firebase Auth and Space Grotesk / DM Serif design conventions, and reads all privileged data through database-role-protected `/v1/admin` API routes. The UI cannot activate models or mutate application data.

## Local development

From the repository root, start the backend/database/routing services using the existing setup (see `QUICKSTART.md`), then run:

```powershell
cd frontend4admin
Copy-Item .env.example .env.local
npm ci
npm start
```

Run the commuter app in a separate terminal with `cd frontend; npm start`. Start the backend and its dependencies from the repository root in another terminal. The two React development servers remain separate.

CRA serves the admin app at `http://localhost:3001`; API calls default to `http://localhost:8000`. The backend's default development CORS origins include port 3001. Use an existing admin account. Configure Firebase public web-app identifiers through ignored `.env.local` values named `REACT_APP_FIREBASE_API_KEY`, `REACT_APP_FIREBASE_AUTH_DOMAIN`, `REACT_APP_FIREBASE_PROJECT_ID`, and `REACT_APP_FIREBASE_APP_ID`. These identifiers are public client configuration, not service credentials. Without Firebase configuration, sign-in falls back to `/v1/auth/login` only when legacy authentication is enabled. Role authorization is always enforced by the API.

## Test and build

```powershell
npm test -- --watchAll=false
npm run build
```

## Docker Compose

Build the independent admin service from the repository root:

```powershell
docker compose up -d --build frontend4admin
```

The service binds to `127.0.0.1:8081` by default (`ADMIN_PORT` can override the host port). Its `/api` proxy targets the existing backend service. The production Compose overlay removes the direct host port and the existing Caddy service exposes the UI at `https://<PUBLIC_HOST>/admin/`. Caddy forwards only that path to the admin static service; other paths continue to the existing commuter frontend. API requests continue through the existing commuter frontend Nginx `/api` proxy. Firebase sign-in requires the production host to be registered as an authorized domain.

## Data and limitations

The admin endpoints are protected by the existing `require_admin` dependency, which resolves the user's current role from the database. The dashboard polls overview telemetry every 30 seconds and uses bounded provider-call history. Collector liveness, request latency history, request error rates, and route decision traces are not currently persisted and are labelled unavailable. Research summaries and predictions are read from generated files in `backend/evaluation/v2/`; historical research scores are never represented as live traffic performance. No research model is activated by this application.
