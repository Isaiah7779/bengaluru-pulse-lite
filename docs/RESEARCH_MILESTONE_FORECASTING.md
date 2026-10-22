# Research milestone: validated short-horizon forecasting

_Status 2026‑10‑22: step M1 implemented and running; M2–M5 designed. No forecasting
accuracy is claimed — there is not yet enough data to measure any._

## Question

Can a model predict the speed ratio (current ÷ free-flow speed) at Bengaluru's
monitored road points 30, 60 and 120 minutes ahead **more accurately than simple
baselines**, measured on data that did not exist when the model was built?

## Current state (inspected)

| Component | State |
|---|---|
| Collection | 26 points every 30 min (TomTom flow), running since 2026‑10‑22 03:16 UTC |
| Offline pipeline (`forecasting/pipeline.py`) | chronological split, 3 baselines, ridge/GBM, activation gate; refuses to run below 14 days |
| Serving (`segment_model.py`) | only `active` models; only evaluated horizons |
| Prospective logging (`forecasting/online.py`) | **new (M1)** — baselines logged every sweep; actuals attached afterwards |
| Defects fixed during this audit | collector could not write models/reports (read-only dirs); API could not see collector-trained artifacts (unshared volume) |

## Definitions

* **Time grid** — 30-minute UTC buckets. An observation belongs to the bucket of its
  `observed_at`, which is the collector's fetch time (TomTom flow responses carry no
  measurement timestamp; documented limitation).
* **Target** — mean speed ratio of a point's observations in the target bucket.
  No interpolation; a bucket without observations has **no actual** and is counted
  as missing.
* **Forecast origin** — the bucket containing the forecast time; a point is
  forecast only if observed in that bucket.
* **Horizons** — 30, 60, 120 minutes (1, 2, 4 buckets).
* **Information rule** — a forecast may use only observations with
  `observed_at < made_at` (tested in `test_logging_ignores_observations_after_now`).
* **Baselines** — persistence (origin value); seasonal naive (same bucket one week
  before the target); historical average (mean of all earlier same weekday and
  time-of-day buckets). A baseline without enough history is skipped, never
  substituted.
* **Errors** — MAE (primary), RMSE, bias (mean of prediction − actual), with n,
  pending and missing counts. **Paired** comparison restricts all candidates to the
  same (point, target, horizon) triples.

## Milestones

| | Deliverable | Data needed | Exit criterion |
|---|---|---|---|
| **M1** ✅ | Prospective baseline logging + actuals + report (`python -m forecasting.online report`, `GET /v1/admin/forecast/online`) | — | running; 8 tests pass |
| M2 | Data-quality report per point: coverage %, gaps, confidence, road class, sweep jitter | 7 days | ≥ 90 % bucket coverage on ≥ 20 points |
| M3 | First baseline comparison: persistence vs seasonal naive vs historical average (paired, prospective) | 14 days (2 weekly samples) | report generated from logged predictions; no model yet |
| M4 | Offline model evaluation with `forecasting.pipeline segments` (chronological; train < validation < test) | ≥ 14 days, target 28 days | model registered; activated only if test MAE ≥ 5 % below the best baseline on every horizon with ≥ 500 test samples |
| M5 | **Prospective validation** of the candidate model: log its forecasts alongside the baselines for ≥ 7 further days; compare paired MAE on data collected after training | M4 + 7 days | activation in routing only if it also beats the best baseline prospectively |

Earliest dates, if collection runs without interruption: M2 ≈ 2026‑10‑29,
M3/M4 ≈ 2026‑11‑05, M5 ≈ 2026‑11‑12. These are calendar estimates, not results.

## Next implementation steps (small, testable)

1. **M2 data-quality report** — per-point bucket coverage and gap list from
   `traffic_observations`; add to the admin freshness page.
2. **Log model forecasts** — when a `candidate` model exists, log its predictions
   through the same `PredictionRecord` path (registered under its own model version)
   so it is compared with baselines on identical triples.
3. **Prospective gate** — extend `predictor.active_model` so activation also requires
   a prospective paired MAE improvement (M5), not only the offline test result.
4. **Snapshot exports for the report** — export the aggregated error tables (not raw
   TomTom observations) for the academic write-up.

## Threats to validity

* 26 sample points ≠ city-wide traffic; results describe those points only.
* Fetch time ≠ measurement time; TomTom's own smoothing interval is unknown.
* Collection gaps (laptop sleep, Docker stopped) remove buckets; reports count them.
* One provider (TomTom); provider-side changes would shift the series.
* Weather and incidents are not yet model features; add only after baselines are established.

## What must not happen

* No accuracy claim before M4/M5 numbers exist.
* No random splits, no interpolated targets, no use of observations after the forecast time.
* No publication of raw TomTom observations until their terms are confirmed (see RELEASE_READINESS.md).
