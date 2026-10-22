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
| Same Wi-Fi (LAN) | http://192.168.1.7:8080 | 200 from the laptop's LAN address; **iPhone Safari: opened and planned a route (verified by the owner)** |
| Temporary public HTTPS (Cloudflare quick tunnel) | printed by `cloudflared` at each start; on 22 Oct: `https://plus-obtain-sherman-knight.trycloudflare.com` | page 200; `/api/health/ready` all `ok`; place search; live traffic-timed route; the frontend's own API calls all 200 in a browser; admin API without token → 401; **iPhone Safari: opened (verified by the owner)** |

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
* Quick tunnels are meant for testing, not production; for a permanent URL see §8a.
* **Browser "Deceptive site" warnings.** On 23 Oct 2026 Google Safe Browsing (used by
  Chrome and Safari) flagged the quick-tunnel hostname then in use as "trying to trick
  visitors into sharing personal info". Its TLS certificate was valid
  (`*.trycloudflare.com`, Google Trust Services). The likely trigger is a password sign-in
  page on an anonymous `trycloudflare.com` name. Check a hostname at
  `https://transparencyreport.google.com/safe-browsing/search?url=<hostname>`. Do not tell
  users to click through; use a stable domain (§8a).

## 8a. Stable domain with a named Cloudflare Tunnel (prepared)

A named tunnel gives a permanent `https://pulse.<your-domain>` address with Cloudflare's
certificate, and still opens no inbound ports. It runs as the opt-in `tunnel` service in
`docker-compose.yml` (image `cloudflare/cloudflared:2026.9.3`), which starts and restarts
with the stack. Everything below is on Cloudflare's free plan. Only the domain itself costs
money, and you already own it.

**1. Put the domain on Cloudflare** (one time; changes who answers DNS for the domain):
1. Sign up or sign in at <https://dash.cloudflare.com> → **Add a domain** → enter the domain →
   choose the **Free** plan.
2. Cloudflare imports existing DNS records. **Compare them with your current registrar's
   DNS list** and add anything missing, especially MX/TXT records if the domain receives
   e-mail. Otherwise mail can break when the nameservers switch.
3. At your registrar, replace the nameservers with the two Cloudflare shows. If DNSSEC is
   on at the registrar, turn it off first. Cloudflare can re-enable it later.
4. Wait until the domain shows **Active** in Cloudflare. This is usually minutes, but can
   take up to 24 h.

**2. Create the tunnel** (Cloudflare dashboard → **Zero Trust** → **Networks** → **Tunnels**):
1. **Create a tunnel** → type **Cloudflared** → name it `bengaluru-pulse`.
2. On the install screen, choose **Docker** and copy only the **token**: the long value after
   `--token`. It is a secret, so don't paste it into chat, commits or screenshots.
3. **Public hostname**: subdomain `pulse` (or any), your domain, service type **HTTP**, URL
   **`frontend:80`**. That is the Docker service name, reached inside the compose network.
4. Save. Cloudflare creates the DNS record automatically.

**3. Run it on this laptop.** Add to the root `.env` (git-ignored):

```
CLOUDFLARE_TUNNEL_TOKEN=<the token>
COMPOSE_PROFILES=tunnel
```

```bash
docker compose up -d tunnel
docker compose logs --tail 20 tunnel     # look for "Registered tunnel connection"
```

`COMPOSE_PROFILES=tunnel` makes a normal `docker compose up -d` include the tunnel from now
on. Without a token the service does not start, so nothing breaks.

**4. After it works:**
* Stop the quick tunnel; it is no longer needed.
* Firebase → Authentication → Settings → **Authorized domains**: add `pulse.<your-domain>`.
* Android app: *Account → Server* → `https://pulse.<your-domain>`. For distributed builds,
  set `EXPO_PUBLIC_API_BASE_URL=https://pulse.<your-domain>/api` (now a stable address).
* Optional: in Cloudflare, **SSL/TLS → Edge Certificates → Always Use HTTPS** = on.

**Rotate the token** (if it leaks): Zero Trust → Tunnels → `bengaluru-pulse` → **Refresh
token**, update `.env`, then run `docker compose up -d tunnel`.

## 9. Mobile app

### Backend URL configuration

Web and mobile use **one backend API**: the same FastAPI endpoints behind nginx at
`<origin>/api`. `mobile/src/api.ts` chooses the backend in this order (none is a secret):

1. **A server set on the device**: *Account → Server* (tested with `GET /health` before
   saving; stored in the device keystore). An installed APK/IPA can follow a changing
   address, such as a temporary tunnel, without a rebuild. Enter e.g.
   `https://<name>.trycloudflare.com`; `/api` is added automatically.
2. **Build configuration**: `EXPO_PUBLIC_API_BASE_URL`, inlined when the bundle is built
   (`mobile/.env` or the EAS build environment). Use this only for a **stable** HTTPS URL;
   never bake a temporary tunnel URL into a distributed build.
3. **Development only**: the laptop's LAN address from the Expo dev server,
   `http://<LAN-IP>:8080/api` (verified: the dev-server manifest advertises `192.168.1.7`).

Nothing else is guessed: no `localhost` (on a phone that is the phone itself) and no
emulator alias. Without a server, the app explains where to set one. The Traffic and Account
screens show the server in use. No API keys are in the mobile bundle (verified: none of the
backend secrets appear in an exported iOS bundle).

**Plain HTTP:** release builds on Android and iOS allow only HTTPS by default. A LAN
`http://` address works with development builds and Expo Go; installed release builds need
an HTTPS server (the tunnel, or a future permanent HTTPS host).

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

**Verified by the owner on the iPhone (Safari):** the tunnel URL and the LAN URL open, and route
planning displays a route. **Not verified:** installing or launching the native Expo app on the
iPhone — mobile-web success does not establish native iOS installation.

## 10. Platform support

All clients use the same backend API. Status as of 22 Oct 2026:

| Platform | How users run it | Status and evidence |
|---|---|---|
| Android phones/tablets — browser | Chrome/Edge/Firefox → LAN or HTTPS URL | responsive layout verified at 375×812 and 768×1024 (emulated, Chromium); **not tested on a physical Android device** |
| Android phones/tablets — app | install the APK, set the server (§9) | **release APK built** (`dist/bengaluru-pulse-v2-android-1.0.0-arm-release.apk`, 34.6 MB, Android 7.0+ / API 24, arm64-v8a + armeabi-v7a, signature verified); **not installed on a physical device or emulator** |
| iPhone/iPad — browser | Safari → LAN or HTTPS URL | **iPhone: verified by the owner** (tunnel URL, LAN URL, route planning); iPad not tested |
| iPhone/iPad — app | development or ad hoc build (§9) | configuration and iOS bundle verified (`expo-doctor` 20/20, 640 modules); **not built or installed** — needs a paid Apple Developer account (or a Mac with Xcode) |
| Windows desktop | Chrome/Edge/Firefox → http://localhost:8080, LAN or HTTPS URL | verified in Chromium at 1280×800 and 1024×768; Edge (Chromium-based) expected to match; Firefox not tested |
| macOS desktop | Safari/Chrome/Firefox → LAN or HTTPS URL | not tested (no Mac available); same responsive web app |
| Linux desktop | Chrome/Firefox → LAN or HTTPS URL | not tested (no Linux desktop available); same responsive web app |

Web browser requirements: a current evergreen browser with JavaScript; location access
needs HTTPS (the tunnel/HTTPS host) or `localhost`. Browsers block GPS on plain-HTTP LAN
addresses, so on the LAN URL use search or map-picking instead of "my location".

### Desktop installers: not built (assessment)

Everything the desktop needs (map, search, routes, traffic, accounts, admin) already runs
in the browser, and the web app can be added as a standalone window from Chrome/Edge
(*Install app*) because it ships a web manifest; that install flow was not tested here.
A native wrapper (Tauri or Electron) would add a Rust or Electron toolchain, per-OS builds
and code signing (Windows SmartScreen and Apple notarization need paid certificates), and
update distribution, while still requiring the same backend. It brings no user-visible
capability for this project, so no desktop installer is produced.

### Manual test steps for devices not available here

1. **Android browser:** same Wi-Fi → open `http://<laptop-LAN-IP>:8080` → plan Koramangala → Hebbal → open a route's steps → Traffic tab.
2. **Android APK:** copy the APK to the phone → install → *Account → Server* → enter the HTTPS URL → *Test and save* → Navigate → plan a route.
3. **iPad / macOS / Linux / Firefox:** open the HTTPS URL → plan a route → resize/rotate the window → check that the map and controls stay usable.


### Android APK: build and install

The APK is built locally from the generated native project (`mobile/android`, created by
`npx expo prebuild`); no Expo or Google account is needed.

```bash
cd mobile
npx expo prebuild --platform android --no-install      # sync native project with app.json (non-destructive)
cd android
# Git Bash; JAVA_HOME = a JDK 17, ANDROID_HOME = the Android SDK
./gradlew assembleRelease -PreactNativeArchitectures=armeabi-v7a,arm64-v8a
# → android/app/build/outputs/apk/release/app-release.apk
```

Verified on 22 Oct 2026: build exit 0; `apksigner verify` passes (v2 signature);
`aapt2 dump badging`: package `org.bengalurupulse.app` 1.0.0, minSdk 24, targetSdk 36,
ABIs arm64-v8a and armeabi-v7a; permissions location + internet (+ vibrate, and biometric
from `expo-secure-store`, unused); storage and overlay permissions removed via
`android.blockedPermissions`. The JavaScript bundle is embedded; no server address and no
secret is baked in (SHA-256 `6a1e8f6a…bca9e6`).

**Signing:** the release build is signed with the template's *debug* keystore. It installs
on devices but cannot be published on Google Play. For Play, create your own upload key, or
use `eas build --profile production` (AAB) with an Expo account; both need your approval.

**Install:** copy the APK to the phone (USB, cloud drive or chat) → open it → allow
"install unknown apps" for that source → install. Or with USB debugging:
`adb install dist/bengaluru-pulse-v2-android-1.0.0-arm-release.apk`. Then *Account → Server* →
enter the current HTTPS address → *Test and save*.

**EAS (optional, account required):** `mobile/eas.json` defines `preview` (internal APK) and
`production` (Play AAB). Running `npx eas-cli@latest build -p android --profile preview` needs
an Expo account login (free tier available); not run.
