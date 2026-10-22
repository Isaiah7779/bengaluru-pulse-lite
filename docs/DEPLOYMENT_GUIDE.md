# Deployment guide

**Status (22 Oct 2026):** the full stack runs and is verified **locally** with Docker
Compose. It is **not publicly deployed**: that needs a hosting account only the
project owner can create. The production configuration below is prepared but has
**not been executed on a real server**. Cost so far: ₹0.

## 1. Prerequisites

| Item | Local | Production server |
|---|---|---|
| OS | Windows 10/11, macOS or Linux | Ubuntu 24.04 (tested target: Oracle Cloud Always Free Ampere A1) |
| Docker | Docker Desktop with Compose ≥ 2.24 | `docker.io` + `docker-compose-v2` |
| RAM / disk | ≥ 4 GB for Docker; ≈ 5 GB disk | ≥ 4 GB (measured need ≈ 1.5–2 GB); ≈ 10 GB disk |
| Shell | Bash (Git Bash on Windows) | Bash |
| Network | internet for images and the OSM download | ports 80 and 443 open; a DNS name pointing at the server |
| Optional | TomTom developer API key | same |

Measured resources: three OSRM servers ≈ 0.8 GB RAM and ≈ 1.4 GB of graph files;
backend ≈ 0.3 GB; PostGIS 0.2–0.5 GB; graph build peak ≈ 0.6 GB per profile.

## 2. Configuration

| File | Purpose | Required values |
|---|---|---|
| `backend/.env` (from `backend/.env.example`) | backend settings for local use | optional `TOMTOM_API_KEY`, `JWT_SECRET` |
| `.env` (from `.env.example`, project root) | compose variables | local: optional; production: `PUBLIC_HOST`, `POSTGRES_PASSWORD`, `JWT_SECRET` (≥ 32 chars), optional `TOMTOM_API_KEY` |

Both `.env` files are gitignored; never commit or share them. Generate secrets with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`.

Key defaults (see `backend/.env.example`): TomTom budget 2,000 calls/day
(`TOMTOM_DAILY_BUDGET`), flow polling every 30 min, incidents hourly, weather every
30 min. Do not shorten the polling intervals: the free TomTom tier allows 2,500
requests per day and the collector already uses ≈ 1,270.

## 3. Startup (local)

```bash
# 1. road graphs (one time; skip if data/osm, data/osrm-foot, data/osrm-bicycle exist)
bash infrastructure/osrm/prepare_graphs.sh "$(pwd)/data"
# 2. configuration
cp backend/.env.example backend/.env        # then edit TOMTOM_API_KEY / JWT_SECRET
# 3. start
docker compose up -d --build
# 4. place search data and first administrator (one time)
docker compose run --rm -v "$(pwd)/data/osm:/data:ro" backend python -m geocoding.gazetteer /data/bengaluru.osm.pbf
docker compose exec backend python -m auth.bootstrap --email you@example.org --name "Your Name"
```

Steps 3 and 4 were run as written during the R4 audit (step 4 against a temporary
database: 68,761 places loaded, administrator created). See
[TEST_REPORT.md](TEST_REPORT.md) for the step 1 reproduction result.

## 4. Verification

```bash
docker compose ps                                   # all services Up; backend/osrm/postgres "healthy"
curl http://localhost:8000/health                   # {"status":"ok",...}
curl http://localhost:8000/health/ready             # every check "ok" (tomtom "not_configured" without a key)
curl -X POST http://localhost:8000/v1/routes -H "Content-Type: application/json" \
  -d '{"origin":{"lat":12.9698,"lon":77.75},"destination":{"lat":12.8456,"lon":77.6603}}'
```

Then open http://localhost:8080, plan a route, and sign in as the administrator to see
**Admin → System health**. Collection is working when `docker compose logs collector`
shows `Flow sweep: {'stored': 26, ...}` every 30 minutes.

## 5. Shutdown

```bash
docker compose stop      # pause; data kept
docker compose down      # remove containers; data volumes kept
```

`docker compose down -v` **deletes the database and all collected observations**.

## 6. Production on one server (prepared, not executed)

Why one server: no verified free platform-as-a-service can hold the three full-city
OSRM graphs (memory plus persistent disk). Free-tier facts checked on 22 Oct 2026:

| Option | Facts found | Fits? |
|---|---|---|
| **Oracle Cloud Always Free (Ampere A1)** | reportedly 2 OCPU / 12 GB since mid-2026; card verification; idle reclamation | **Yes (recommended)** |
| Google Cloud e2-micro | 1 GB RAM | No |
| Render / Koyeb free | ~512 MB, no persistent disk | API only, no OSRM |
| Hugging Face Docker Spaces | paid plan required | No |
| Neon free Postgres | 0.5 GB, PostGIS | database only |

Steps (owner):

1. Create the VM (Ubuntu 24.04), open TCP 80/443, point a DNS name at it.
2. On the VM:
   ```bash
   sudo apt-get install -y docker.io docker-compose-v2 git
   git clone https://github.com/Isaiah7779/bengaluru-pulse-lite.git && cd bengaluru-pulse-lite
   git checkout v2-build          # after it has been pushed
   bash infrastructure/osrm/prepare_graphs.sh "$(pwd)/data"
   cp .env.example .env           # set PUBLIC_HOST, POSTGRES_PASSWORD, JWT_SECRET, TOMTOM_API_KEY
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker compose run --rm -v "$(pwd)/data/osm:/data:ro" backend python -m geocoding.gazetteer /data/bengaluru.osm.pbf
   docker compose exec backend python -m auth.bootstrap --email admin@yourdomain --name Admin
   ```
3. Verify `https://PUBLIC_HOST/api/health/ready` (Caddy obtains the certificate automatically).

The production overlay sets `ENVIRONMENT=production` (refuses to start without a
strong `JWT_SECRET`), limits CORS to `https://PUBLIC_HOST`, publishes only ports 80/443
(through Caddy) and does not load `backend/.env`.

Operations: schedule `docker compose exec postgres pg_dump -U pulse -Fc pulse > backup.dump`;
graphs are mounted read-only and never rebuilt automatically.

## 7. CI/CD

`.github/workflows/ci.yml` (tests, builds, migration check, Docker smoke test) and
`.github/workflows/deploy.yml` (manual SSH deploy) are written; their commands were
run locally, but **they have never run on GitHub** because `v2-build` has not been pushed.

## Mobile app

```bash
cd mobile
npm ci
echo "EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000" > .env   # Android emulator → host machine
npx expo run:android            # needs an emulator (Android Studio) or a USB device
```

For a USB phone without exposing the backend on Wi-Fi: `adb reverse tcp:8000 tcp:8000`
and `adb reverse tcp:8081 tcp:8081`, with `EXPO_PUBLIC_API_BASE_URL=http://localhost:8000`.
The existing debug APK needs the Metro dev server (`npx expo start`); it does not
contain the JavaScript bundle. **The mobile app has not yet been run on a device or emulator.**
