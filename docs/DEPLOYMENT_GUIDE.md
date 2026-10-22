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
run locally. After `v2-build` was pushed (22 Oct 2026), the first GitHub run of
`ci.yml` passed all four jobs (backend, frontend, mobile, docker):
https://github.com/Isaiah7779/bengaluru-pulse-lite/actions/runs/39756763914.
`deploy.yml` has not been run (no server exists).

## 8. External access for review and demos (verified 22 Oct 2026)

### How the frontend and backend communicate

The browser loads the React app from nginx (port 8080) and calls the API on the
**same origin** under `/api/...`; nginx forwards `/api/*` to FastAPI inside Docker.
Only port 8080 is published on the network. The API (8000), Postgres (5433) and
OSRM (5000–5002) are bound to `127.0.0.1` and are not reachable from other devices
(verified: the LAN address refuses connections on those ports).

### Verified URLs

| Access | URL | Verified |
|---|---|---|
| This laptop | http://localhost:8080 | page 200, API readiness all `ok` |
| Same Wi-Fi (LAN) | http://192.168.1.7:8080 | 200 from the laptop's own LAN address; **phone test pending** (some routers isolate Wi-Fi clients) |
| Temporary public HTTPS (Cloudflare quick tunnel) | printed by `cloudflared` at each start; on 22 Oct: `https://plus-obtain-sherman-knight.trycloudflare.com` | page 200; `/api/health/ready` all `ok`; place search; live traffic-timed route; the frontend's own API calls all 200 in a browser; admin API without token → 401 |

The LAN address comes from `ipconfig` (Wi-Fi adapter) and changes with the network.
The Windows network profile is *Public*; Docker Desktop's firewall rule already allows
inbound connections on that profile.

### Start the temporary HTTPS tunnel (PowerShell)

`cloudflared` is installed (winget, v2026.10.3) but is not on PATH, so use its full path:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --no-autoupdate --url http://localhost:8080
```

Copy the `https://<random-words>.trycloudflare.com` URL it prints; stop it with Ctrl+C.

* No Cloudflare account and no cost; the URL is **random and changes at every start**.
* It works only while the laptop is on, Docker is running, the internet is connected
  and the `cloudflared` process keeps running.
* Only port 8080 (nginx) is exposed; admin endpoints require an administrator token.
  Anyone with the URL can register and plan routes, which spends the shared TomTom
  budget (capped at 2,000 calls/day) — stop the tunnel when not demonstrating.
* Quick tunnels are meant for testing, not production; for a permanent URL see §6.

## 9. Mobile app

### Backend URL configuration

`mobile/src/api.ts` chooses the backend in this order (the value is not a secret):

1. `EXPO_PUBLIC_API_BASE_URL`, inlined when the bundle is built, e.g.
   `https://<name>.trycloudflare.com/api`. Put it in `mobile/.env` (gitignored; see `mobile/.env.example`).
2. Otherwise, during `npx expo start`, the laptop's LAN address taken from the Expo dev
   server: `http://<LAN-IP>:8080/api` (verified: the dev-server manifest advertises `192.168.1.7`).
3. Otherwise the Android-emulator alias `http://10.0.2.2:8080/api`.

`localhost` is never used (on a phone it is the phone). The app's Traffic screen shows the
server in use. No API keys are in the mobile bundle (verified: none of the backend secrets
appear in an exported iOS bundle).

### iPhone: supported testing routes (SDK 58)

The project uses **Expo SDK 58.0.17** (React Native 0.88). Expo's SDK 58 changelog
(15 Oct 2026) states the App Store Expo Go for SDK 58 "will be released within a few
weeks". Until then the App Store Expo Go cannot open this project: the dev server's
manifest requests `exposdk:58.0.0`, matching the "requires a newer version of Expo Go"
error seen on the iPhone.

| Route | Status | Requirements |
|---|---|---|
| Expo Go (App Store) | blocked until Expo publishes the SDK 58 Expo Go | then: same Wi-Fi, `npx expo start --lan`, scan the QR code |
| iOS development build via EAS Build | possible | Expo account + **paid Apple Developer Program** membership for device provisioning — owner approval needed |
| Development build via Xcode | possible | a Mac with Xcode (free Apple ID gives 7-day signing) |
| Downgrade the project to SDK 57 for today's Expo Go | possible, not done | dependency downgrade — owner approval needed |
| **Web app in iPhone Safari** | **available now** | open the LAN or tunnel URL above |

Android: a debug APK was built earlier (`npx expo prebuild` created `mobile/android`); it
loads its JavaScript from the dev server. Run with `npx expo run:android` on an emulator
or a USB device (`adb reverse tcp:8081 tcp:8081` keeps Metro off the network).

### Start the dev server for a phone on the same Wi-Fi

```powershell
cd C:\Users\IZY\OneDrive\Desktop\BengaluruPulseLite\mobile
npx expo start --lan
```

For remote testing through the tunnel, create `mobile/.env` containing
`EXPO_PUBLIC_API_BASE_URL=https://<current-tunnel>.trycloudflare.com/api`, then start again.

### Troubleshooting

| Symptom | Fix |
|---|---|
| iPhone: "project requires a newer version of Expo Go" | expected until SDK 58 Expo Go reaches the App Store; use Safari with the web app, or a development build |
| Phone cannot open http://192.168.1.7:8080 | same Wi-Fi? router "client/AP isolation" off? run `ipconfig` to confirm the IP; or use the tunnel URL |
| `cloudflared` is not recognized | use the full path above, or open a new terminal after installing |
| App shows "Cannot reach the server at …" | the URL shown is wrong for this network: set `EXPO_PUBLIC_API_BASE_URL` or restart `npx expo start --lan` |
| Tunnel URL stopped working | the `cloudflared` process ended or the laptop slept; start it again (new URL) |

**Not yet verified:** opening the LAN or tunnel URL on the physical iPhone, and any launch
of the mobile app on an iPhone.
