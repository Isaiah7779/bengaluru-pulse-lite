# Results and limitations

Every number below was measured on this project's code and data on 22 October 2026.
Evidence types are labelled: **[live]** observed on the running system with real
providers; **[test]** automated test; **[offline]** chronological evaluation on the
public dataset; **[prospective]** forecasts logged before the outcome was known.
Synthetic test fixtures are never used as evidence here.

## 1. What is completed versus validated

| Area | Infrastructure | Validated result |
|---|---|---|
| Full-city routing (car, bicycle, walk; motorcycle on car graph) | complete | yes — 5 benchmark trips [test, live] |
| Diverse alternatives + dedup | complete | yes [test, live] |
| Traffic-timed comparison, shortcut/longcut labels | complete | yes — definitions tested exhaustively; live example below |
| Data collection (flow, incidents, weather) | complete, running | yes — counts below [live] |
| Offline forecasting pipeline (chronological, baselines, gate) | complete | yes, as a **negative result** on the public dataset [offline] |
| Forecasting on own observations | pipeline + prospective logging complete | **no — insufficient data** |
| Community verification | complete | mechanism tested [test]; no real submissions |
| Auth / roles / security | complete | yes [test, live] |
| Web app | complete | yes — browser walkthrough [live] |
| Mobile app | builds | **not run on a device** |
| Public deployment | configuration prepared | **not deployed** |

## 2. Routing

| Trip | Reference distance | Result |
|---|---|---|
| Whitefield → Marathahalli | 7.6 km | pass [test] |
| Whitefield → Electronic City | 24.7 km | pass [test] |
| Indiranagar → Yeshwanthpur | 14.7 km | pass [test] |
| Airport (KIA) → Whitefield | 38.0 km | pass [test] |
| Koramangala → Hebbal | 15.3 km | pass [test] |

* Candidates: OSRM's native alternatives gave 0–2 per trip; the engine considered
  10–13 candidates per request and returned up to 5 routes with pairwise geometric
  similarity < 0.85 [test, live].
* Mode realism (Indiranagar → Yeshwanthpur, free-flow): car 51 km/h, bicycle 14.1 km/h,
  walk 5.0 km/h [live].
* Avoid tolls: Electronic City → Kengeri via NICE Road 27.47 km / 22.7 min;
  avoiding tolls 26.42 km / 31.6 min [live].
* Traffic-aware labels [live, 22 Oct 2026, TomTom live traffic]: Whitefield → Electronic
  City — **shortcut** 21.4 km / 66 min vs reference 24.7 km / 77 min; **longcut**
  26.4 km / 71 min. Koramangala → Hebbal — reference 16.3 km at 62 min with 9.1 min
  TomTom delay (free-flow 41.2 min, TomTom typical 58.2 min). These are single
  observations at one moment; traffic changes, so labels on another day may differ.
* Latency: 2–3 s per request with TomTom timing, 1.4–2.3 s without [live, local laptop].

## 3. Data collected (own observations) [live]

Collection started 22 Oct 2026 03:16 UTC.

Snapshot queried 22 Oct 2026 08:37 UTC (collection continues; numbers grow every 30 min):

| Data | Count | Notes |
|---|---|---|
| Traffic-flow observations | 312 | 26 points × 12 sweeps, 03:16–08:36 UTC (5.3 h); every sweep covered all 26 points |
| Weather observations | 72 | 6 areas × 12 sweeps |
| Incidents seen / active | 970 / 336 | TomTom incident sweeps (hourly) |
| TomTom calls today | 351 | of the enforced 2,000/day budget (free tier 2,500) |

Raw observations are private research data and are not included in the submission
(TomTom storage terms unconfirmed).

## 4. Forecasting

### 4.1 Offline, public daily dataset [offline]

Dataset: `backend/Banglore_traffic_Dataset.csv`, 8,936 rows, 16 roads, daily,
2022‑01‑01 → 2024‑08‑09, provenance undocumented. Chronological split by target
date; test period 2024‑02‑01 → 2024‑08‑09.

| Horizon | Candidate | Test MAE | Test RMSE | R² | n |
|---|---|---|---|---|---|
| 1 day | persistence | 20.217 | 29.124 | −0.541 | 1791 |
| 1 day | seasonal naive | 19.737 | 28.529 | −0.478 | 1791 |
| 1 day | **historical average** | **15.985** | **20.492** | 0.237 | 1791 |
| 1 day | ridge (selected on validation) | 16.079 | 20.606 | 0.229 | 1791 |
| 7 days | persistence / seasonal naive | 19.661 | 28.414 | −0.462 | 1774 |
| 7 days | **historical average** | **16.008** | **20.528** | 0.237 | 1774 |
| 7 days | ridge | 16.097 | 20.612 | 0.230 | 1774 |

* **No model beat the historical-average baseline** (ridge 0.6 % worse); the model was
  registered as *candidate*, not activated.
* Why: lag-1 autocorrelation per road averages −0.008 (range −0.074…0.068),
  day-of-week means differ by only 1.15 points, and 43.5 % of values sit at the cap
  (100). Real traffic has strong daily/weekly structure; this dataset behaves like
  random draws around road means, consistent with synthetic data.
* V1's reported R² 0.96 reproduced only with **same-day** volume and speed as inputs
  (chronological R² 0.962, MAE 2.98) — estimation, not forecasting. Without them:
  R² 0.232, MAE 16.03.

### 4.2 Own observations

**Status: insufficient data — no forecasting claim is made.**

* Offline evaluation (`python -m forecasting.pipeline segments`) refuses to run below
  14 days of data; at 08:37 UTC the series spanned 5.3 hours.
* Prospective logging (`forecasting/online.py`) started 07:58 UTC. Snapshot at 08:37 UTC:

| Baseline | Horizon | Resolved (n) | MAE | RMSE | Bias | Pending |
|---|---|---|---|---|---|---|
| persistence | 30 min | 26 | 0.0479 | 0.0920 | −0.0265 | 52 |
| persistence | 60 min | 0 | – | – | – | 78 |
| persistence | 120 min | 0 | – | – | – | 78 |
| seasonal naive / historical average | all | 0 | – | – | – | not logged: need ≥ 1 week of history |

Units: speed ratio (current ÷ free-flow, typically 0.2–1.0). The 26 resolved values
are **one forecasting round at one time of day** at 26 points — far too few for any
conclusion about accuracy, and with only one baseline available there is nothing to
compare against yet. They demonstrate that the prediction-versus-actual pipeline works
on real data, nothing more. Current figures: `docker compose exec collector python -m forecasting.online report`.

## 5. Limitations

1. **Forecasting is not validated.** No model has beaten baselines; evaluation on own
   data requires ≥ 14 days (≈ 5 Nov 2026 if collection is continuous).
2. **Coverage:** traffic flow at 26 sample points only; one provider (TomTom).
3. **Timestamps:** an observation's time is the collector's fetch time; TomTom flow
   responses carry no measurement time.
4. **Collection gaps:** the collector stops when the laptop/Docker stops; sweeps drift
   ≈ 20 s per cycle, which can leave occasional 30-minute buckets without data
   (counted as missing, never filled).
5. **Public dataset quality:** provenance unknown, likely synthetic; results on it do not
   transfer to real traffic.
6. **Single-moment observations:** the live routing examples are not statistically
   representative.
7. **Motorcycle** uses the car graph; two-wheeler restrictions are not modelled.
8. **Mobile** not run on a device; iOS not built.
9. **Not deployed publicly**; CI never run on GitHub.
10. **Terms:** TomTom storage terms unconfirmed — collected observations must not be published.

## 6. Next steps

1. Keep the collector running continuously for ≥ 14 days (ideally 28).
2. M2: per-point data-quality report (coverage, gaps) — after 7 days.
3. M3/M4: paired prospective baseline comparison, then `python -m forecasting.pipeline segments`.
4. M5: log a candidate model's forecasts prospectively for ≥ 7 days before allowing routing to use it.
5. Deploy on a free VM; test the mobile app on an emulator or device.
See [RESEARCH_MILESTONE_FORECASTING.md](RESEARCH_MILESTONE_FORECASTING.md).
