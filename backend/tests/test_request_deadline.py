"""End-to-end request deadline: stalled weather, TomTom and database work cannot hold a route request.

The stalls below block with time.sleep, like a database call inside the TomTom
quota guard or the weather cache would: asyncio cannot interrupt them, so the
engine runs that work in worker threads on copies of the routes and abandons it
at the deadline.
"""

import asyncio
import time

import pytest

from core.settings import get_settings
from providers.tomtom import RouteTiming
from routing.engine import RoutingEngine
from routing.schemas import RouteRequestV2

from fakes import FakeOSRM, FakeTomTom, NullWeather, osrm_route, straight, via

O, D = (12.9352, 77.6245), (13.0358, 77.5970)
DIRECT = straight(O, D)
EAST = via(O, (12.985, 77.6650), D)
STALL_S = 4.0
BUDGET_S = 1.6


class StalledWeather:
    async def at(self, lat, lon, when):
        time.sleep(STALL_S)  # blocking, like the weather cache's database read
        return {"time": "2026-11-06T00:00:00+00:00", "source": "stalled"}


class StalledTomTom(FakeTomTom):
    """The first `fast` timings answer at once; the rest block (like a stuck quota query)."""

    def __init__(self, fast=0):
        super().__init__()
        self.fast = fast

    async def route_timing(self, coordinates, **kw):
        self.calls += 1
        if self.calls > self.fast:
            time.sleep(STALL_S)
        return await super().route_timing(coordinates, **kw)


class NoTraffic:
    configured = False


def _engine(tomtom=None, weather=None, use_database=False, **settings):
    s = get_settings().model_copy(update={"route_plan_deadline_s": BUDGET_S, "osrm_extra_candidates_max": 0,
                                          "osrm_spur_repair_max": 0, **settings})
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(EAST)])
    return RoutingEngine(s, tomtom=tomtom or NoTraffic(), weather=weather or NullWeather(),
                         clients={"driving": osrm}, use_database=use_database)


def _timed_plan(engine):
    """Time until the response is ready (as a server would send it).

    asyncio.run() then waits for the abandoned worker threads before closing its
    loop; a long-running server loop does not, so that wait is not part of a request.
    """

    req = RouteRequestV2(origin={"lat": O[0], "lon": O[1]}, destination={"lat": D[0], "lon": D[1]})

    async def run():
        t0 = time.monotonic()
        res = await engine.plan(req)
        return res, time.monotonic() - t0

    return asyncio.run(run())


def test_stalled_weather_does_not_hold_the_request():
    res, elapsed = _timed_plan(_engine(weather=StalledWeather()))
    assert elapsed < BUDGET_S + 0.5
    assert len(res.routes) == 2
    assert {s.name: s.status for s in res.data_sources}["weather"] == "unavailable"
    assert res.weather is None


def test_stalled_tomtom_returns_free_flow_routes_and_says_so():
    res, elapsed = _timed_plan(_engine(tomtom=StalledTomTom(fast=0)))
    assert elapsed < BUDGET_S + 0.5
    assert len(res.routes) == 2 and all(r.traffic is None for r in res.routes)
    traffic = {s.name: s for s in res.data_sources}["tomtom_traffic"]
    assert traffic.status == "unavailable" and "request time limit" in traffic.detail
    assert res.comparison_basis == "free_flow"
    assert all("request time limit" in r.traffic_note for r in res.routes)
    assert any("did not finish within" in w for w in res.warnings)


def test_partly_stalled_tomtom_keeps_the_timings_that_arrived():
    res, elapsed = _timed_plan(_engine(tomtom=StalledTomTom(fast=1)))
    assert elapsed < BUDGET_S + 0.5
    timed = [r for r in res.routes if r.traffic is not None]
    assert len(timed) == 1  # the one timing that arrived in time is kept intact
    assert {s.name: s.status for s in res.data_sources}["tomtom_traffic"] == "degraded"
    # The response stays consistent: one recommended route, one reference, valid classifications.
    assert sum(r.recommended for r in res.routes) == 1 and sum(r.is_reference for r in res.routes) == 1
    assert all(r.classification["type"] for r in res.routes)


def test_stalled_database_evidence_is_abandoned(monkeypatch):
    engine = _engine(use_database=True)
    calls = []

    def stalled(self, kept, *a, **kw):
        calls.append(kw.get("timeout_s"))
        time.sleep(STALL_S)  # a query stuck on a lock or a slow database
        raise AssertionError("not reached in time")

    monkeypatch.setattr(RoutingEngine, "_attach_incidents", stalled)
    res, elapsed = _timed_plan(engine)
    assert elapsed < BUDGET_S + 0.5
    assert len(res.routes) == 2 and all(not r.incidents for r in res.routes)
    db = {s.name: s for s in res.data_sources}["observations_db"]
    assert db.status == "unavailable" and "request time limit" in db.detail
    assert calls and 0 < calls[0] <= BUDGET_S  # statement timeout passed to the queries


def test_everything_stalled_at_once_still_ends_on_time(monkeypatch):
    monkeypatch.setattr(RoutingEngine, "_attach_incidents", lambda self, *a, **kw: time.sleep(STALL_S))
    engine = _engine(tomtom=StalledTomTom(), weather=StalledWeather(), use_database=True)
    res, elapsed = _timed_plan(engine)
    assert elapsed < BUDGET_S + 0.5
    assert res.routes


def test_endpoint_starts_the_clock_and_returns_503_when_planning_overruns(client, app, monkeypatch):
    from api import routing_api

    class SlowEngine:
        async def plan(self, body, deadline_at=None):
            # (+0.05 s: Windows' monotonic clock ticks every ~16 ms)
            assert deadline_at is not None and deadline_at - time.monotonic() <= BUDGET_S + 0.05
            await asyncio.sleep(STALL_S)

    monkeypatch.setattr(routing_api, "SAFETY_NET_S", 0.0)
    app.dependency_overrides[routing_api.get_engine] = lambda: SlowEngine()
    app.dependency_overrides[routing_api.request_deadline] = lambda: time.monotonic() + BUDGET_S
    try:
        body = {"origin": {"lat": 12.97, "lon": 77.59}, "destination": {"lat": 12.93, "lon": 77.62}}
        t0 = time.monotonic()
        r = client.post("/v1/routes", json=body)
        assert time.monotonic() - t0 < BUDGET_S + 1.0
        assert r.status_code == 503 and r.json()["error"]["code"] == "routing_deadline_exceeded"
    finally:
        app.dependency_overrides.clear()


def test_deadline_is_measured_from_request_arrival(client):
    from types import SimpleNamespace

    from api import routing_api

    settings = get_settings().model_copy(update={"route_plan_deadline_s": 20.0})
    arrived = time.monotonic() - 7.0  # e.g. a slow sign-in check already used 7 s
    request = SimpleNamespace(state=SimpleNamespace(received_at=arrived))
    assert routing_api.request_deadline(request, settings) == pytest.approx(arrived + 20.0)
    # The middleware records arrival on every request.
    r = client.get("/health")
    assert r.status_code == 200


def test_trip_save_failure_returns_the_route_with_a_warning(client, app, user_headers, monkeypatch):
    from api import routing_api

    app.dependency_overrides[routing_api.get_engine] = lambda: _engine()
    monkeypatch.setattr(routing_api, "_save_trip", lambda db, trip, deadline: "trip not saved (test)")
    try:
        body = {"origin": {"lat": O[0], "lon": O[1]}, "destination": {"lat": D[0], "lon": D[1]}, "save_trip": True}
        r = client.post("/v1/routes", json=body, headers=user_headers)
        assert r.status_code == 200 and r.json()["trip_id"] is None
        assert "trip not saved (test)" in r.json()["warnings"]
    finally:
        app.dependency_overrides.clear()
