# Project Status — Bengaluru Pulse V2

_Last updated: 2026-10-22 — living resume file. Update at every phase boundary._

Branch: `v2-build` (local only, not pushed). Baseline snapshot commit `2e42577`.

## Phase progress

| Phase | State | Notes |
|---|---|---|
| 0 Audit | ✅ done | PROJECT_AUDIT.md, IMPLEMENTATION_ROADMAP.md |
| 1 Foundation | ⏳ in progress | |
| 2–15 | pending | |

## Environment notes for resuming

* Python: `.venv-v2/Scripts/python.exe`; run backend tests from `backend/`.
* Docker Desktop must be started manually; OSRM graph in `data/osm/`.
* `backend/.env` holds the real TomTom key — never print or commit it.
* Repo lives in OneDrive: avoid walking `node_modules`/`.venv*`/`tools/`.

## Blockers

* Public deployment requires owner-created hosting accounts (see roadmap).
