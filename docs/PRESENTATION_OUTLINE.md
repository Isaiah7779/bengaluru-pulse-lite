# Presentation outline (11 slides, ≈ 12 minutes)

Screenshots referenced below can be taken from the running app at http://localhost:8080.
Use only real screenshots and the measured numbers given here.

### 1. Title
* Bengaluru Pulse V2 — Evidence-Based Route Planning and Traffic Forecasting for Bengaluru
* Team, guide, institution, R4 review date
* **Notes:** one-sentence pitch: "Route planning that shows its evidence, and an honest forecasting study."

### 2. Problem and motivation
* Heavy, variable congestion; navigation apps rarely show *why* a route is recommended or whether a time is measured or estimated.
* No transparent way to verify local shortcuts.
* V1 audit: dashboard numbers were simulated; walking/cycling used the car graph.
* **Visual:** none or a single photo/map of Bengaluru.
* **Notes:** be explicit that the V1 findings motivated the rebuild.

### 3. Objectives and scope
* O1–O10 table (condensed) from FINAL_PROJECT_REPORT §3 with status ticks.
* Scope: Bengaluru metro, 4 modes, route planning (not live guidance), local deployment.
* **Notes:** point out which objectives are partially achieved (forecasting, mobile, deployment).

### 4. Literature and gap
* OSRM/MLD [2,3]; alternative routes [4]; HMM map matching [6]; short-term forecasting reviews [7]; deep spatio-temporal models need dense sensors [8,9]; time-ordered evaluation [10,11].
* Gap: transparent, reproducible system + honest baseline-first evaluation (not a new model).
* **Notes:** do not claim novelty over Google Maps.

### 5. System architecture
* **Diagram:** ARCHITECTURE.md mermaid (web/mobile → nginx → FastAPI → OSRM ×3, PostGIS, TomTom, Open-Meteo; collector).
* **Notes:** why three OSRM servers (profile name in the URL is ignored).

### 6. Routing method
* Reference route → 10 corridor candidates → filters (detour, U-turn) → geometric dedup → TomTom timing with 8 % length check → one comparison basis.
* Shortcut = shorter **and** faster; Longcut = longer **and** faster; noise thresholds.
* **Visual:** small flow diagram; screenshot of route cards with badges.

### 7. Live demo (or screenshots)
* Koramangala → Hebbal (car, live traffic); explanation panel; walking route; future departure.
* **Screenshots needed:** results panel; *Why this route*; Data sources list.
* **Notes:** follow DEMO_SCRIPT.md.

### 8. Data collection
* 26 monitored points every 30 min, incidents hourly, weather every 30 min; quota guard (≈ 1,270 of 2,500 free TomTom calls/day).
* Validation, de-duplication, staleness, retention.
* **Screenshot:** Traffic page; Admin → Data freshness.
* **Notes:** state collection start date (22 Oct 2026) and current counts from RESULTS_AND_LIMITATIONS.md.

### 9. Forecasting results (honest)
* Public dataset, chronological test: historical average MAE 15.985 (1 d) vs ridge 16.079 → no improvement; lag-1 autocorrelation −0.008.
* V1 R² 0.96 = same-day estimation; without same-day inputs R² 0.23.
* Own data: insufficient (≥ 14 days needed); prospective prediction-vs-actual logging running.
* **Visual:** table of test MAE by candidate (from ML_PIPELINE.md).
* **Notes:** emphasise this is a measured negative result, not a failure of the system.

### 10. Testing and quality
* 115 backend tests (incl. live OSRM benchmarks, migrations), 7 frontend tests, mobile build checks.
* Security checks (401/403, no secret leakage), failure injection, 15 defects found and fixed.
* **Visual:** test summary table from TEST_REPORT.md.

### 11. Limitations, future work, conclusion
* Not publicly deployed; no validated forecasting model; 26 sample points; native mobile app not launched on a device (web app verified on iPhone Safari); temporary tunnel only; TomTom terms pending.
* Next: ≥ 14 days data → evaluate models prospectively; deploy on a free VM; device testing.
* **Notes:** close with the one-line conclusion from FINAL_PROJECT_REPORT §12.

(Backup slide, optional) **Security and roles** — RBAC matrix from SECURITY.md.
