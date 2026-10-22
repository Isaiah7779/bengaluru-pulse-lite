# Research summary (academic report companion)

## Problem

Commuters in Bengaluru choose routes under heavy, variable congestion. Navigation
apps show a "fastest" route but rarely explain *why*, rarely separate measured from
estimated data, and do not let a community verify local shortcuts. This project asks:

1. **RQ1 – Candidate diversity.** Can practical, diverse route alternatives be
   generated on a full-city OSM graph beyond OSRM's native alternatives?
2. **RQ2 – Evidence-based recommendation.** Can each recommendation be explained
   from identifiable data sources, on a comparable travel-time basis?
3. **RQ3 – Forecasting.** Does a learned model forecast Bengaluru road congestion
   better than simple baselines on chronologically held-out data?
4. **RQ4 – Shortcut verification.** Can community trips be turned into verified
   shortcuts without trusting unvalidated submissions?

## Methods

* Routing: OSRM MLD on three Lua profiles; corridor via-point candidates; symmetric
  geometric similarity for dedup; U-turn spur filtering (ROUTING.md).
* Traffic: TomTom timing of each candidate's *own geometry* with a length-match
  check (≤ 8 %) to prevent attributing another road's ETA (ROUTING.md).
* Classification: strict shortcut/longcut definitions with noise thresholds and a
  common time basis.
* Forecasting: chronological split by target time, three baselines, ridge/GBM,
  single test evaluation, activation gate (ML_PIPELINE.md).
* Community: GPS cleaning, map matching on the vehicle's graph, comparison on a
  common basis, ≥ 3 independent confirmations, admin review.

## Results (measured)

* **RQ1.** For all five benchmark trips the engine returned valid routes with
  navigation steps; OSRM alone gave 0–2 alternatives (e.g. 0 for Whitefield →
  Marathahalli), while corridor generation considered 10–13 candidates per request,
  returning up to 5 geometrically distinct routes (pairwise similarity < 0.85, tested).
* **RQ2.** Every response lists its data sources with status and timestamps;
  explanations cite TomTom delay, typical time, geometry match, incidents on the
  route and monitored-point observations. Example (live, 2026‑10‑22): Whitefield →
  Electronic City produced a shortcut (21.4 km / 66 min vs 24.7 km / 77 min reference)
  and a longcut (26.4 km / 71 min) on TomTom live traffic.
* **RQ3.** On the public daily dataset, the historical average achieved test MAE
  15.985 (1 d) / 16.008 (7 d); ridge 16.079 / 16.097; persistence 20.217 / 19.661.
  No model beat the baseline; the dataset shows near-zero lag-1 autocorrelation
  (−0.008) and no weekly pattern (1.15-point spread), indicating no forecastable
  temporal structure. The V1 R² of 0.96 is reproduced only when same-day volume and
  speed are inputs (estimation, not forecasting); without them R² = 0.23.
* **RQ4.** The lifecycle is implemented and tested (9 tests); with no real
  community submissions yet, no shortcut has been verified.

## Threats to validity

* Public dataset provenance unknown and likely synthetic; results on it do not
  generalise to real traffic.
* Collected TomTom data covers 26 sample points and, at the time of writing, hours
  rather than weeks — too little for forecasting conclusions.
* TomTom is a single commercial source; its predictions for future departures are
  provider-modelled, not ours.
* Benchmark latencies were measured on one laptop with local Docker.

## Future work

1. Collect ≥ 4 weeks of observations and re-run Track B (30/60/120 min).
2. Extend monitored points along corridors used by recommended routes.
3. Inject verified community shortcuts as routing candidates.
4. Explore spatiotemporal GNNs once a dense, long history exists and a non-graph model has been beaten.
5. User study on whether evidence-based explanations change route choice.
