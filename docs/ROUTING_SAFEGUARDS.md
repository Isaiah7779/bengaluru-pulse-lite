# Routing safeguards (developer reference)

Implementation detail of the Phase 1 routing changes (November 2026): extra candidate
routes, spur repair, route selection and labels, private-road and motorcycle checks,
the request time limit and the audit-trip tests. [ROUTING.md](ROUTING.md) is the
concise overview.

This file is deliberately **not** in the documentation assistant's corpus
(`backend/assistant/corpus.py` `ALLOWLIST`): its implementation vocabulary competed
with the user-facing routing answers and lowered retrieval quality. Keep user-facing
facts in ROUTING.md and code-level detail here.

## Extra candidate routes

Beyond OSRM's own alternatives and the corridor routes (ROUTING.md, *Candidate
generation*):

* **Extra via-routes** (`OSRM_EXTRA_CANDIDATES_MAX`, default 4, also used on Render):
  a via-point at the middle of the straight origin-destination line, two beside the
  middle of the reference route (8 % of the trip, 400 m – 2.5 km), then two on the
  straight line at 1/3 and 2/3. OSRM snaps them to the nearest car road, which surfaces
  shorter-distance paths over connecting streets (`routing/engine.py`:
  `direct_waypoints`, `detour_waypoints`, `extra_waypoints`).
* **Spur repair** (`OSRM_SPUR_REPAIR_MAX`, default 3): a via-route that drives into a
  dead end and back is re-requested through the point where it left the road
  (shortest first), so OSRM still enforces one-ways and turn restrictions
  (`routing/geometry.py`: `spur_entry_points`).

## Selection and labels (`RoutingEngine._select`, `_label`)

1. Candidates that fail the private-road or motorcycle checks (below) are removed.
2. Filters: distance ≤ 1.5 × reference + 1 km, duration ≤ 1.5 × reference + 3 min;
   via-routes still retracing ≥ 120 m of road (U-turn spurs) are dropped.
3. The reference is kept, then the shortest-distance candidate if it is shorter than
   every kept route by more than max(50 m, 1 %), then the rest fastest-first.
4. A candidate is a near-duplicate when more than 70 % of its length, or of a kept
   route's length, lies within 40 m of a kept route (`ROUTE_MAX_SHARED_FRACTION`), or
   its own part is under 500 m (`ROUTE_MIN_UNIQUE_M`). The shortest-distance route is
   exempt, so distance-optimal and time-optimal routes appear side by side.
5. Every rejection is counted in the response's `selection.rejected`
   (`invalid`, `restricted_access`, `motorcycle_restricted`, `impractical_detour`,
   `u_turn_spur`, `near_duplicate`, `over_route_limit`, `timed_out`); when only one
   route survives, `selection.note` (also a warning) says why instead of showing a
   near-copy.
6. Labels: `fastest` (lowest ETA on the comparison basis), `shortest_distance`
   (shortest route found; the car graph optimises time, so not a guaranteed shortest
   path) and `least_traffic_delay` (only when TomTom timed 2+ routes).
   `shared_max_pct` is each route's largest overlap with another route shown.

## Private and restricted roads (`routing/access.py`)

A via-point snapped inside a gated campus or layout (e.g. RMZ Ecospace, Bellandur)
makes OSRM drive through it. A candidate that uses a private or destination-only road
anywhere except the trip's own start or end is dropped (`restricted_access`). Two
signals, either one rejects:

* `backend/routing/car_access_restricted.bin`: 64-bit hashes of every segment of the
  43,660 car-routable OSM ways whose motor-car access (car.lua order: motorcar,
  motor_vehicle, vehicle, access) is private, destination, customers, delivery, permit
  or residents (1.5 MB, ~13 MB RAM; summary in `car_access_restricted.json`). Matched
  exactly, segment by segment, so a public road beside or crossing a campus is never
  flagged.
* OSRM's `restricted` road class, when the server reports classes. Our own servers
  do; the public FOSSGIS server Render uses returns none, so there only the extract
  check runs. `data_sources.private_road_check` states which ran.

If OSRM's default route itself fails a check, the fastest remaining route becomes the
reference; if nothing remains the request fails with 422 `no_legal_route`.

Limits: only what OSM tags is known (untagged gated roads and gates on public roads
count as public), and a road re-tagged after the extract may be missed by a public
server with newer data. A few major roads are tagged private in OSM (e.g. RMZ Eco World
Underpass, Classic Orchards Main Road, Nandi Hill Road); routes through them mid-trip
are rejected.

## Motorcycle restrictions (`routing/restrictions.py`)

OSRM has no motorcycle profile and car.lua ignores `motorcycle=*`. Routes on the 123
OSM ways tagged `motorcycle=no` (Bengaluru-Mysuru Expressway, Goraguntepalya Flyover;
`backend/routing/motorcycle_restricted.json`) are removed for motorcycles, by exact
node-pair matching plus a near match (≥ 300 m within 8 m) for servers whose OSM data
differs slightly. If every candidate uses them, the engine retries with
`exclude=motorway` (own servers only) and via-points beside the restricted stretch,
else returns 422 `no_legal_route`. Two-wheeler rules missing from OSM, and two-wheeler
speeds, are not modelled.

Both data files are rebuilt from the graph extract with:

    cd backend && python -m routing.restrictions build ../data/osm/bengaluru.osm.pbf

Rebuild them whenever the OSRM graphs are rebuilt; nothing enforces this.

## Request time limit

`ROUTE_PLAN_DEADLINE_S` (default 20 s) limits a route request end to end. The clock
starts when the request reaches the app: the request-ID middleware
(`core/errors.py`) records the arrival time before the sign-in check, and
`api/routing_api.request_deadline` turns it into the deadline.

* Routing-engine calls (primary, via-routes, spur repairs, motorcycle bypass) must
  finish min(5 s, 25 %) before the limit, 15 s by default. Unfinished ones are
  cancelled and the routes already found are used; `selection.rejected.timed_out`
  counts them and a warning says so. Without a primary route, or with no legal route
  before the limit, the API answers 503 `routing_deadline_exceeded` (retryable).
* Traffic-provider calls, incident and monitored-point lookups and weather then run
  concurrently until 0.5 s before the limit. The provider's quota guard, the weather
  cache and the evidence queries make blocking database calls that asyncio cannot
  interrupt, so each runs in a worker thread on copies of the routes and is abandoned
  at the limit. Only results that arrived are copied back, so traffic can be partial.
  Evidence queries also get a PostgreSQL `statement_timeout`. A stalled step is shown
  in `data_sources` and a warning; the routes are returned without it.
* Saving the trip (`save_trip`) runs with a `statement_timeout` of the time left (at
  least 0.5 s); if it fails, the route is returned with a warning and no `trip_id`.
* An outer `asyncio.wait_for` on the whole plan is the safety net.

Not covered: Render's cold start of a sleeping free instance, and network/TLS time
before the request reaches the app. Blocking work inside the sign-in check (a Firebase
key fetch, or waiting for a database connection: connect timeout 10 s, pool wait up to
30 s) counts against the limit but cannot be interrupted, so a stall there can push a
response past 20 s. Abandoned worker threads run until their own call ends (bounded by
provider timeouts and `statement_timeout`) and occupy the default thread pool meanwhile.

Tests: `tests/test_request_deadline.py` (stalled weather, TomTom and database work,
endpoint 503, trip-save failure) and the deadline tests in `tests/test_engine.py`.

## Audit trips (`tests/test_routing_trips_live.py`)

The six routing-audit trips (Whitefield ↔ Marathahalli, Whitefield → Electronic City,
Marathahalli → Indiranagar, Electronic City → Koramangala, Whitefield → Hebbal) in car
and motorcycle mode, plus Kengeri → Ramanagara (Bengaluru-Mysuru Expressway, tagged
`motorcycle=no`). They run against the local OSRM when it is up, and against the public
server Render uses with `PULSE_LIVE_PUBLIC_OSRM=1`; CI has no OSRM, so there they are
skipped and the fake-OSRM tests in `test_engine.py` and `test_restrictions.py` (real OSM
ways in `tests/fixtures/osm_restriction_samples.json`) cover the same rules. Assertions
are structural (route count, geometry, labels, ≤ 70 % overlap, no motorcycle=no or
private roads mid-trip, single-route note, deadline), never exact ETAs.
