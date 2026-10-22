# R4 submission checklist

## Deliverables

| Item | Path | Status |
|---|---|---|
| Final project report | `docs/FINAL_PROJECT_REPORT.md` | done |
| README (install, setup, Docker, usage, troubleshooting, shutdown) | `README.md` | done |
| User guide | `docs/USER_GUIDE.md` | done |
| Deployment guide | `docs/DEPLOYMENT_GUIDE.md` (`docs/DEPLOYMENT.md` points to it) | done |
| Test report | `docs/TEST_REPORT.md` | done |
| Results and limitations | `docs/RESULTS_AND_LIMITATIONS.md` | done |
| Demo script | `docs/DEMO_SCRIPT.md` | done |
| Presentation outline | `docs/PRESENTATION_OUTLINE.md` | done |
| Supporting design docs | `docs/ARCHITECTURE.md`, `ROUTING.md`, `TRAFFIC.md`, `ML_PIPELINE.md`, `DATABASE.md`, `SECURITY.md`, `RESEARCH.md`, `RESEARCH_MILESTONE_FORECASTING.md` | done |
| Audit trail | `docs/PROJECT_AUDIT.md`, `RELEASE_READINESS.md`, `FINAL_SYSTEM_AUDIT.md`, `PROJECT_STATUS.md` | done |
| Source ZIP (current) | `dist/bengaluru-pulse-v2-r4-source-v2.zip` | see "ZIP" below |
| Source ZIP (earlier, kept) | `dist/bengaluru-pulse-v2-r4-source.zip` | superseded; predates the mobile URL and iPhone results |
| Slides (PowerPoint/PDF) | not produced — build from `PRESENTATION_OUTLINE.md` | **team** |
| Screenshots for slides | not produced — capture from the running app | **team** |

## ZIP

Built with `git archive` from the committed `v2-build` tree, so **only tracked files** are
included. Gitignored files can never enter it: `.env` files and backups, `data/`
(OSM extracts, OSRM graphs), virtual environments, `node_modules/`, `frontend/build/`,
`mobile/android`, the APK, caches, `backend/runtime/`, `backend/models/`.

Additionally excluded from the ZIP (kept in the repository):

| File | Why excluded |
|---|---|
| `backend/traffic.db` | local SQLite database (12 legacy V1 prediction rows); not used by V2 |
| `backend/traffic_model.pkl` | 38 MB legacy untuned V1 model; not used by the app (it uses `traffic_model_tuned.pkl`); regenerate with `python backend/train_model.py` |

Included on purpose: the public research dataset `backend/Banglore_traffic_Dataset.csv`
(needed to reproduce the ML results), `traffic_model_tuned.pkl` and encoders (legacy
`/predict` endpoint), `backend/evaluation/v2/*.json` (aggregate metrics only, no raw
traffic observations), `.env.example` templates (placeholders only).

Never include: `backend/.env`, root `.env`, `mobile/.env`, `data/.env.backup-*`, any
database dump, collected TomTom observations, `mobile/android/**`, `*.apk`.

The reviewer needs to run `infrastructure/osrm/prepare_graphs.sh` (graphs are not in the
ZIP, ≈ 1.4 GB) and supply their own TomTom key (optional).

## Pre-submission checks

- [x] Backend and frontend tests pass (see TEST_REPORT.md for exact numbers and time)
- [x] App verified running through nginx (http://localhost:8080) with readiness all `ok`
- [x] README commands checked against the real files and scripts
- [x] No secret values in tracked files or git history (checked by value, not printed)
- [x] ZIP contents listed and scanned (see TEST_REPORT.md, "Packaging")
- [ ] Slides prepared from PRESENTATION_OUTLINE.md (team)
- [ ] Demo rehearsed with DEMO_SCRIPT.md on the presentation laptop (team)
- [ ] Decide on items needing approval (below)

## Decisions needing the owner's approval

1. Push the latest local commits of `v2-build` (the branch itself was pushed on 22 Oct and CI passed).
2. Untrack `backend/traffic.db` and `backend/traffic_model.pkl` from git (files stay on disk).
3. Handle secrets in the OneDrive-synced folder (`backend/.env`, `data/.env.backup-20261022`).
4. Delete the regenerable 2.3 GB `mobile/android` folder (OneDrive sync size).
5. Align collector sweeps to the clock (≈ +13 TomTom calls/day; prevents occasional missing 30-min buckets).
6. Public deployment: create an Oracle Cloud Always Free VM.
