# Deployment

**Current state (2026‑10‑22): not publicly deployed.** The complete stack runs and is
verified locally with Docker Compose. A public deployment needs a hosting account
that only the owner can create (agents may not create accounts or enter payment
verification). Everything else — images, production overlay, HTTPS, CI, deploy
workflow and graph preparation — is ready. Actual cost so far: **₹0**.

## 1. Local (verified)

```bash
# one-time: build the three OSRM graphs (or reuse data/ from this machine)
bash infrastructure/osrm/prepare_graphs.sh "$(pwd)/data"
cp .env.example .env                  # local defaults are fine
# backend/.env: TOMTOM_API_KEY=… (optional), see backend/.env.example
docker compose up -d --build
docker compose run --rm -v "$(pwd)/data/osm:/data:ro" backend python -m geocoding.gazetteer /data/bengaluru.osm.pbf
docker compose exec backend python -m auth.bootstrap --email you@example.org --name "You"
```
Web: http://localhost:8080 · API docs: http://localhost:8000/docs · readiness: `/health/ready`.

## 2. Hosting options evaluated (constraints checked 2026‑10‑22)

Resource needs (measured): 3 OSRM servers ≈ 0.8 GB RAM and ≈ 1.4 GB graph files;
backend ≈ 0.3 GB; PostGIS ≈ 0.2–0.5 GB; graph rebuild peak ≈ 0.6 GB; database
currently < 100 MB (gazetteer + days of observations).

| Option | Free-tier facts found | Fits? |
|---|---|---|
| **Oracle Cloud Always Free (Ampere A1)** | Reported reduced to 2 OCPU / 12 GB RAM in mid‑2026; 200 GB block storage; idle instances may be reclaimed; card verification at sign-up | **Yes — whole stack on one VM (recommended)** |
| Google Cloud e2-micro | 1 GB RAM, US regions only, card required | No (OSRM ×3 + API + DB exceed 1 GB) |
| Render free web service | ~512 MB, sleeps after 15 min, no persistent disk; free Postgres expires after 30 days | API only, without OSRM; DB unsuitable |
| Koyeb free | 1 instance, 512 MB, 0.1 vCPU | API only, without OSRM |
| Hugging Face Spaces | Docker Spaces now require a paid plan | No |
| Neon free Postgres | 0.5 GB storage, 100 CU-h/month, PostGIS, scale-to-zero | DB only — viable with retention |
| GitHub Pages / Cloudflare Pages | static hosting | Web front-end only |

**Why not split across free PaaS:** no verified ₹0 PaaS can hold the full-city OSRM
graphs (memory + persistent disk). Splitting would force either a degraded routing
graph or a paid service — both violate the project constraints. A single Always
Free VM keeps every component, persistent storage and HTTPS at ₹0.

## 3. Production on one VM (prepared, not executed)

1. Create an Oracle Cloud account (owner), launch an Ubuntu 24.04 Ampere A1 VM
   (2 OCPU / 12 GB), open TCP 80/443 in the security list and host firewall.
2. Point a DNS name at the VM (any domain you control, or a free dynamic-DNS name).
   No domain purchase is required by this project.
3. On the VM:
   ```bash
   sudo apt-get install -y docker.io docker-compose-v2 git
   git clone https://github.com/Isaiah7779/bengaluru-pulse-lite.git && cd bengaluru-pulse-lite
   bash infrastructure/osrm/prepare_graphs.sh "$(pwd)/data"        # ~10 min, ~2 GB download+graphs
   cp .env.example .env   # set PUBLIC_HOST, POSTGRES_PASSWORD, JWT_SECRET, TOMTOM_API_KEY
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   docker compose run --rm -v "$(pwd)/data/osm:/data:ro" backend python -m geocoding.gazetteer /data/bengaluru.osm.pbf
   docker compose exec backend python -m auth.bootstrap --email admin@yourdomain --name Admin
   ```
4. Caddy obtains the TLS certificate automatically. Check `https://PUBLIC_HOST/api/health/ready`.
5. Enable continuous deployment: add repository secrets `DEPLOY_HOST`, `DEPLOY_USER`,
   `DEPLOY_SSH_KEY`, `DEPLOY_PATH` and variable `PUBLIC_HOST`, then run the
   **Deploy (manual)** workflow.
6. Mobile: build with `EXPO_PUBLIC_API_BASE_URL=https://PUBLIC_HOST/api` (EAS Build
   free tier requires an Expo account, or `npx expo run:android` locally).

Production overlay guarantees: `ENVIRONMENT=production` (JWT secret mandatory),
CORS limited to `https://PUBLIC_HOST`, only Caddy publishes ports, development
`backend/.env` not loaded.

Operational notes: keep the VM above Oracle's idle thresholds (the collector and
OSRM help); schedule `pg_dump` backups; OSRM graphs survive restarts (read-only
mounts, never rebuilt automatically); update graphs by re-running
`prepare_graphs.sh` and restarting the three OSRM services.

## 4. CI/CD

* `.github/workflows/ci.yml` (push/PR): backend tests with a PostGIS service +
  `alembic upgrade/check`; frontend tests + production build; mobile typecheck +
  Android bundle export; Docker image builds + `/health` smoke test.
* `.github/workflows/deploy.yml`: manual dispatch only; SSH deploy + public smoke test.
* Status: workflows written and the commands they run were executed locally;
  **they have not run on GitHub** because the branch has not been pushed
  (pushing to the public repository is left to the owner).

## 5. Costs

| Item | Cost |
|---|---|
| Development so far (local machine, free APIs) | ₹0 |
| Oracle Always Free VM, Caddy/Let's Encrypt, GitHub Actions (public repo), OSM, Open-Meteo, TomTom free tier | ₹0 |
| Domain | ₹0 if an existing/free DNS name is used; none was purchased |
