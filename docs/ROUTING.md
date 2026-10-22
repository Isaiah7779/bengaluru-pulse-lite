# Routing

## Road graphs and vehicle modes

| Mode | Graph | Lua profile | Status | Traffic applied |
|---|---|---|---|---|
| car | `data/osm/bengaluru.osrm` | car.lua | dedicated | TomTom (`travelMode=car`) |
| motorcycle | car graph | car.lua | **car-graph approximation** (disclosed in every response) | TomTom (`travelMode=motorcycle`) |
| bicycle | `data/osrm-bicycle/` | bicycle.lua | dedicated | not applicable |
| walk | `data/osrm-foot/` | foot.lua | dedicated | not applicable |

* Source: OpenStreetMap via Geofabrik *India – Southern Zone* (snapshot 2026‑09‑26),
  cut to lon 77.00–78.00, lat 12.45–13.42 (`infrastructure/osrm/prepare_graphs.sh`).
* **Why separate servers:** OSRM ignores the profile name in the URL. Asking the car
  server for `/route/v1/foot/…` returned the identical car route (verified during the
  audit). Modes therefore map to servers; a mode without its server returns
  `503 mode_unavailable` rather than silently using another graph.
* Measured resources: car graph ≈ 540 MB on disk / ≈ 300 MB RSS; foot ≈ 420 MB /
  ≈ 230 MB; bicycle ≈ 427 MB / ≈ 235 MB. Each build took ~3 min, peak ≈ 0.6 GB RAM.
* Motorcycle limitation: OSRM has no motorcycle profile; restrictions specific to
  two-wheelers are not modelled.

Measured speeds, Indiranagar → Yeshwanthpur (live OSRM): car 14.7 km / 17.2 min
(free-flow), foot 14.39 km / 172.9 min (≈ 5 km/h), bicycle 14.83 km / 62.9 min (≈ 14 km/h).

## Candidate generation

1. OSRM primary route with `alternatives=3` → **reference route** (OSRM's default
   free-flow fastest route for the mode) plus native alternatives.
2. Corridor routes: via-points placed perpendicular to the straight line at
   7 / 14 / 24 / 34 % of the trip length (clamped 300 m – 7 km) on both sides
   (two via-points at 30 % and 70 %), plus two single mid-points at 18 %.
   10 requests, 5 concurrently. Trips under 400 m skip corridors.
3. Filters: distance ≤ 1.5 × reference + 1 km, duration ≤ 1.5 × reference + 3 min;
   corridor routes retracing ≥ 120 m of road already used (U-turn spurs at a
   snapped via-point) are dropped.
4. Geometry-aware dedup: routes resampled every 50 m; similarity = min of the two
   directional fractions within 40 m of the other route; ≥ 0.85 ⇒ duplicate.
5. Up to 5 routes returned (configurable).

## Traffic timing

* TomTom Calculate Route with the candidate's geometry as `supportingPoints`
  (≤ 120 points), `computeTravelTimeFor=all` → live ETA, traffic delay,
  no-traffic time, historic (typical) time.
* Future departures (> 15 min ahead) send `departAt`; TomTom then predicts from
  historical patterns. This is labelled `traffic_predicted` and attributed to TomTom.
* **Reconstruction check:** if TomTom's route length differs from OSRM's by > 8 %,
  TomTom has timed a different road; the timing is rejected and the note explains why.
* Budget: at most 5 timings per request, cached 5 min per geometry/departure bucket,
  under the shared daily TomTom quota (see TRAFFIC.md).

## Comparison basis and preferences

* If the reference route has a valid traffic timing, the comparison basis is that
  traffic basis and only traffic-timed routes are ranked ("comparable"); others are
  listed with their free-flow time and marked not comparable. Otherwise everything
  is compared on OSRM free-flow, with a warning that real traffic is usually slower.

| Preference | Ranking key | Fallback |
|---|---|---|
| fastest | ETA | — |
| shortest | distance | — |
| least_traffic_now | TomTom delay (+0.01·ETA tie-break) | fastest if no traffic; predicted if departure is in the future |
| least_traffic_predicted | TomTom predicted delay | fastest if no traffic; "now" if departing now |
| balanced | 0.60·time + 0.20·distance + 0.10·delay share + 0.10·incidents | — |

Balanced components are relative to the best comparable route (time/best − 1, etc.);
incidents add 0.5 per major/closure and 0.1 per other incident on the route (capped at 1).
These weights are a documented product choice, not a learned model.

Avoid options: `toll`, `motorway`, `ferry` (car and motorcycle only, one at a time;
OSRM's car profile rejects combinations). Verified: Electronic City → Kengeri uses
NICE Road (27.47 km, 22.7 min); with `avoid=toll` it uses the service road
(26.42 km, 31.6 min).

## Shortcut / longcut classification (`routing/classification.py`)

Against the clearly identified reference route, on the **same time basis**:

* **SHORTCUT** — shorter distance **and** shorter travel time.
* **LONGCUT** — longer distance **and** shorter travel time.
* **ALTERNATIVE** — anything else (incl. equal metrics, shorter-but-slower, longer-and-slower).
* **UNCLASSIFIED** — a metric is missing/invalid, or the time bases differ.

Differences within max(50 m, 1 %) distance or max(30 s, 2 %) time are "equal"
(measurement noise). Each label carries the signed differences and a sentence.
If a route lacks a traffic timing while the reference has one, both are compared
on free-flow instead. Tested exhaustively in `tests/test_classification.py`.

Observed on live data (2026‑10‑22, TomTom live traffic): Whitefield → Electronic City
returned a **shortcut** (21.4 km / 66 min vs reference 24.7 km / 77 min) and a
**longcut** (26.4 km / 71 min).

## Evidence attached to each route

* **Incidents on the route:** line incidents count only when ≥ 50 % of them (or
  ≥ 60 m) lies within 20 m of the route; point incidents within 25 m. Closures on
  crossing side-streets are excluded. Walking/cycling show only closures,
  flooding, road works, hazards and accidents.
* **Monitored points:** the nearest point of the TomTom segment to the monitoring
  location must lie within 120 m of the route; observations older than 90 min
  are shown as not fresh.
* **Weather** at the origin for the departure time (Open-Meteo; advisory only, no
  travel-time adjustment).
* **Long-detour warning** when the route exceeds 1.8 × the straight-line distance
  (e.g. destination on a flyover carriageway).

## Benchmarks (live OSRM, `tests/test_integration_live.py`)

| Trip | Reference (km) | Test bounds | Result |
|---|---|---|---|
| Whitefield → Marathahalli | 7.6 | 5–12 | pass |
| Whitefield → Electronic City | 24.7 | 18–35 | pass |
| Indiranagar → Yeshwanthpur | 14.7 | 10–22 | pass |
| Airport (KIA) → Whitefield | 38.0 | 30–50 | pass |
| Koramangala → Hebbal | 15.3 | 11–22 | pass |

Each also asserts navigation steps ending in "Arrive", full geometry, valid
classifications and no near-duplicate routes. Typical latency with TomTom timing:
2–3 s; without TomTom: 1.4–2.3 s per request (local Docker, 8-core laptop).

## Resilience

* OSRM circuit breaker: after a connect failure/timeout a server is treated as
  down for 20 s and requests fail in ~0.3 s instead of waiting on DNS/sockets.
* TomTom failures, quota exhaustion and mismatches degrade to free-flow with an
  explanation per route; routing never fails because of the traffic provider.

## Known limitations

* No turn-by-turn voice guidance or rerouting while driving (route planning only).
* Corridor candidates are geometric heuristics; the k-shortest-paths problem is not solved exactly.
* Community-verified shortcuts are displayed on the map but not injected as candidates.
* Free-flow OSRM durations are optimistic for Bengaluru; the UI says so whenever they are used.
