# Forecasting pipeline

Code: `backend/forecasting/pipeline.py` (train/evaluate/register),
`segment_model.py` (serving), `predictor.py` (activation gate).

```bash
cd backend
python -m forecasting.pipeline research   # public daily dataset
python -m forecasting.pipeline segments   # collected TomTom observations
```

Reports: `backend/evaluation/v2/<task>.json`; registry: `model_versions` and
`evaluation_records` (one row per horizon × split × candidate × metric);
artifacts: `backend/models/*.joblib`.

## Method

1. **Validate** — duplicates, nulls, ranges, share at cap, lag-1 autocorrelation,
   day-of-week spread.
2. **Features** at the forecast origin only: last observed value and its age,
   lags, rolling mean/std, seasonal value, calendar of the *target* time,
   historical average (computed from the training split only).
3. **Chronological split by target time**: train (≈65 %) < validation (15 %) < test (20 %).
4. **Baselines first**: persistence, seasonal naive (same slot one week earlier),
   historical average (series × weekday[/half-hour]).
5. **Models**: ridge regression; HistGradientBoosting (4 settings). Selection on
   validation MAE; the selected model is refit on train+validation and evaluated
   **once** on test.
6. **Metrics**: MAE, RMSE, sMAPE, MAPE, R², bias, n.
7. **Activation gate**: a model is used by routing only if its test MAE is ≥ 5 %
   below the best baseline on **every** horizon with ≥ 500 test samples
   (segments task). Otherwise it is registered as `candidate`.

## Track A — public daily dataset (research)

`Banglore_traffic_Dataset.csv`: 8,936 rows, 16 roads, daily, 2022‑01‑01 → 2024‑08‑09,
~9 roads per day. Provenance undocumented.

**Data validation findings (measured):**

| Check | Value | Interpretation |
|---|---|---|
| Duplicates / nulls / out of range | 0 / 0 / 0 | clean |
| Rows at congestion = 100 (cap) | 43.5 % | heavily censored target |
| Lag-1 autocorrelation per road | mean −0.008 (range −0.074 … 0.068) | **no temporal persistence** |
| Day-of-week mean spread | 1.15 points (of 0–100) | **no weekly seasonality** |

Real urban traffic shows strong daily/weekly patterns and autocorrelation; this
dataset behaves like independent draws around road-specific means, consistent with
synthetic data. That bounds what any forecaster can achieve on it.

**Task:** congestion level per road, 1 day and 7 days ahead. Splits (target time):
train 2022‑01‑02 → 2023‑09, validation 2023‑09‑12 → 2024‑01, test 2024‑02‑01 → 2024‑08‑09.

**Test results (measured, `evaluation/v2/research-daily-congestion.json`):**

| Horizon | Candidate | MAE | RMSE | sMAPE % | R² | n |
|---|---|---|---|---|---|---|
| 1 d | persistence | 20.217 | 29.124 | 30.13 | −0.541 | 1791 |
| 1 d | seasonal naive | 19.737 | 28.529 | 29.54 | −0.478 | 1791 |
| 1 d | **historical average** | **15.985** | **20.492** | 22.73 | 0.237 | 1791 |
| 1 d | ridge (selected) | 16.079 | 20.606 | 22.84 | 0.229 | 1791 |
| 7 d | persistence / seasonal naive | 19.661 | 28.414 | 29.17 | −0.462 | 1774 |
| 7 d | **historical average** | **16.008** | **20.528** | 22.78 | 0.237 | 1774 |
| 7 d | ridge (selected) | 16.097 | 20.612 | 22.91 | 0.230 | 1774 |

Validation MAE (1 d): ridge 16.015, HGB 16.52–17.28, historical average 16.042.
**Conclusion:** no model beats the historical average (ridge is 0.6 % worse on test);
the model is registered as `candidate`, not activated. This is the expected outcome
given the absence of temporal signal.

**Re-examining the V1 model.** V1 reported R² 0.958 from a random split on 492 rows,
using *same-day* traffic volume and speed as inputs. Reproduced on the full dataset:

| Setting | MAE | RMSE | R² |
|---|---|---|---|
| Same-day volume + speed, random split | 3.00 | 4.67 | 0.960 |
| Same-day volume + speed, chronological split | 2.98 | 4.60 | 0.962 |
| Chronological, without same-day measurements | 16.03 | 20.57 | 0.232 |

The V1 accuracy is genuine for **same-day estimation** (congestion correlates 0.84
with same-day volume) but says nothing about forecasting: volume and speed for a
future day are not known in advance. V1 remains available only as the labelled
legacy `/predict` endpoint and is not used for routing.

## Track B — collected TomTom observations (operational)

* Target: speed ratio (current / free-flow) at each monitored point.
* Grid: 30 min; horizons 30 / 60 / 120 min; lags 1, 2, 47 (≈1 day), 335 (1 week);
  rolling 2 h and 24 h; time-of-day/day-of-week of the target.
* Gate: ≥ 14 days of data before any evaluation; then the activation rule above.
* Status (2026‑10‑22): **insufficient data** — 156 observations over 0.1 day. The
  collector retries training daily; the first evaluation becomes possible after
  ~2026‑11‑05 if collection runs continuously.
* Serving: only an `active` model is used; forecasts are offered only for the
  evaluated horizons (within one step); further-ahead requests return no forecast
  rather than an extrapolation.
* Pipeline mechanics (splits, leakage, baselines, registry, gating, serving) are
  verified by `tests/test_forecasting.py` on clearly labelled synthetic fixtures;
  those fixtures are never reported as results.

## Graph neural networks

Not built. A spatiotemporal GNN needs a dense sensor graph with weeks of
high-frequency history. Available data: 16 roads with no topology and no temporal
signal (Track A), and 26 sparse sample points with hours of history (Track B).
Revisit once Track B has several months of data and at least one evaluated
non-graph model to beat.
