"""The six routing-audit trips (plus one motorcycle restriction trip) against live OSRM.

    pytest tests/test_routing_trips_live.py                 # local Docker OSRM (skipped if not running)
    PULSE_LIVE_PUBLIC_OSRM=1 pytest tests/test_routing_trips_live.py   # also the public server Render uses

Assertions are structural (counts, labels, overlap, restriction compliance,
deadline behaviour), never exact ETAs: OSRM data and public-server results
change over time. No TomTom or weather calls are made.
"""

import asyncio
import itertools
import os
import time

import pytest

from core.errors import UpstreamUnavailable
from core.settings import get_settings
from providers.tomtom import ProviderUnavailable
from routing.access import access_restrictions
from routing.engine import RoutingEngine
from routing.geometry import overlap_fraction
from routing.restrictions import motorcycle_restrictions
from routing.schemas import RouteRequestV2

from fakes import FakeTomTom, NullWeather
from test_integration_live import LIVE, reachable

pytestmark = pytest.mark.integration

PLACES = {  # the audit's coordinates (docs: routing audit, 2026-11-05)
    "Whitefield": (12.9698, 77.7499),
    "Marathahalli": (12.9563, 77.7010),
    "Indiranagar": (12.9719, 77.6412),
    "Electronic City": (12.8456, 77.6603),
    "Koramangala": (12.9352, 77.6245),
    "Hebbal": (13.0358, 77.5970),
    "Kengeri": (12.9120, 77.4850),
    "Ramanagara": (12.7209, 77.2799),
}
TRIPS = [
    ("Whitefield", "Marathahalli"),
    ("Marathahalli", "Whitefield"),
    ("Whitefield", "Electronic City"),
    ("Marathahalli", "Indiranagar"),
    ("Electronic City", "Koramangala"),
    ("Whitefield", "Hebbal"),
]
PUBLIC_URL = "https://routing.openstreetmap.de/routed-car"

SERVERS = {
    "local": dict(osrm_url=LIVE["driving"], osrm_corridor_max=10, osrm_max_concurrency=5, osrm_exclude_supported=True),
    # Mirrors render.yaml (public FOSSGIS server: no `exclude`, one call at a time).
    "public": dict(osrm_url=PUBLIC_URL, osrm_corridor_max=4, osrm_max_concurrency=1, osrm_exclude_supported=False,
                   osrm_timeout_seconds=15.0),
}
MIN_ROUTES = {"local": 2, "public": 1}  # local graph is fixed; the public server's data changes


def _available(server: str) -> bool:
    if server == "local":
        return reachable(LIVE["driving"])
    return os.getenv("PULSE_LIVE_PUBLIC_OSRM") == "1" and reachable(PUBLIC_URL)


SERVER_PARAMS = [
    pytest.param(s, marks=pytest.mark.skipif(not _available(s), reason=f"{s} OSRM not available"
                                              + (" (set PULSE_LIVE_PUBLIC_OSRM=1)" if s == "public" else "")))
    for s in SERVERS
]


def _engine(server: str, **overrides) -> RoutingEngine:
    settings = get_settings().model_copy(update={"osrm_foot_url": None, "osrm_bicycle_url": None,
                                                 **SERVERS[server], **overrides})
    tomtom = FakeTomTom(fail=ProviderUnavailable("not configured"))
    tomtom.configured = False
    return RoutingEngine(settings, tomtom=tomtom, weather=NullWeather(), use_database=False)


def _plan(engine: RoutingEngine, a: str, b: str, **kw):
    o, d = PLACES[a], PLACES[b]
    req = RouteRequestV2(origin={"lat": o[0], "lon": o[1]}, destination={"lat": d[0], "lon": d[1]},
                         include_steps=False, **kw)
    return asyncio.run(engine.plan(req))


def _check_common(res, server: str):
    routes = res.routes
    assert routes and res.selection is not None
    for r in routes:
        coords = r.geometry["coordinates"]
        assert len(coords) >= 2 and r.distance_m > 0 and r.eta_s > 0
        assert all(77.0 <= lon <= 78.0 and 12.45 <= lat <= 13.42 for lon, lat in coords)
    assert sum(r.is_reference for r in routes) == 1
    assert sum(r.recommended for r in routes) == 1
    # Roles: exactly one fastest and one shortest-distance route, and they are what they say.
    fastest = [r for r in routes if "fastest" in r.labels]
    shortest = [r for r in routes if "shortest_distance" in r.labels]
    assert len(fastest) == 1 and len(shortest) == 1
    assert fastest[0].eta_s == min(r.eta_s for r in routes)
    assert shortest[0].distance_m == min(r.distance_m for r in routes)
    # Diversity: no two routes are near-duplicates (the shortest-distance route is exempt by design).
    limit = get_settings().route_max_shared_fraction
    for x, y in itertools.combinations(routes, 2):
        if "shortest_distance" in x.labels or "shortest_distance" in y.labels:
            continue
        ca, cb = x.geometry["coordinates"], y.geometry["coordinates"]
        assert max(overlap_fraction(ca, cb), overlap_fraction(cb, ca)) <= limit + 1e-9
    # Private / destination-only roads: never used mid-trip (OSM extract check, works on any server).
    access = access_restrictions()
    assert all(access.through_m(r.geometry["coordinates"]) == 0 for r in routes)
    # Honest single-route fallback.
    if len(routes) == 1:
        assert res.selection.note and res.selection.note in res.warnings
    assert len(routes) >= MIN_ROUTES[server]


@pytest.mark.parametrize("server", SERVER_PARAMS)
@pytest.mark.parametrize("a,b", TRIPS)
def test_audit_trip_car(server, a, b):
    res = _plan(_engine(server), a, b)
    _check_common(res, server)
    shortest = next(r for r in res.routes if "shortest_distance" in r.labels)
    fastest = next(r for r in res.routes if "fastest" in r.labels)
    # Shorter is not automatically faster: a distinct shortest route is never presented as faster.
    if shortest.id != fastest.id:
        assert shortest.distance_m < fastest.distance_m and shortest.eta_s >= fastest.eta_s


@pytest.mark.parametrize("server", SERVER_PARAMS)
@pytest.mark.parametrize("a,b", TRIPS + [("Kengeri", "Ramanagara")])
def test_audit_trip_motorcycle_avoids_motorcycle_no_roads(server, a, b):
    res = _plan(_engine(server), a, b, vehicle="motorcycle")
    _check_common(res, server)
    banned = motorcycle_restrictions()
    assert all(banned.used_length_m(r.geometry["coordinates"]) < 50 for r in res.routes)


@pytest.mark.parametrize("server", SERVER_PARAMS)
def test_kengeri_ramanagara_car_may_use_the_expressway(server):
    res = _plan(_engine(server), "Kengeri", "Ramanagara")
    reference = next(r for r in res.routes if r.is_reference)
    assert motorcycle_restrictions().used_length_m(reference.geometry["coordinates"]) > 1000


@pytest.mark.parametrize("server", SERVER_PARAMS)
def test_tight_deadline_returns_partial_results_or_a_retryable_error(server):
    budget = 1.0
    engine = _engine(server, route_plan_deadline_s=budget, osrm_max_concurrency=1)
    t0 = time.monotonic()
    try:
        res = _plan(engine, "Whitefield", "Hebbal")
    except UpstreamUnavailable as exc:  # the primary route itself did not arrive in time
        assert exc.code == "routing_deadline_exceeded"
    else:
        assert res.routes
        if res.selection.rejected.get("timed_out"):
            assert any("planning limit" in w for w in res.warnings)
    assert time.monotonic() - t0 < budget + 2.0  # bounded; cancellation is prompt
