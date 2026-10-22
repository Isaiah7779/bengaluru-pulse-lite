"""Routing engine behaviour with fake OSRM/TomTom (no network)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from core.errors import AppError, UpstreamUnavailable
from core.settings import get_settings
from providers.tomtom import ProviderUnavailable
from routing.engine import RoutingEngine, corridor_waypoints
from routing.schemas import RouteRequestV2

from fakes import FakeOSRM, FakeTomTom, NullWeather, osrm_route, straight, via

O, D = (12.9352, 77.6245), (13.0358, 77.5970)
DIRECT = straight(O, D)
EAST = via(O, (12.985, 77.6650), D)  # longer corridor (~1.5 km more)
WEST = via(O, (12.985, 77.5700), D)  # much longer corridor


def engine(osrm: FakeOSRM, tomtom=None, **settings_overrides) -> RoutingEngine:
    settings = get_settings().model_copy(update=settings_overrides)
    tomtom = tomtom or FakeTomTom(fail=ProviderUnavailable("not configured"))
    if tomtom.__class__.__name__ == "FakeTomTom" and tomtom.fail and isinstance(tomtom.fail, ProviderUnavailable):
        tomtom.configured = False
    return RoutingEngine(
        settings,
        tomtom=tomtom,
        weather=NullWeather(),
        clients={"driving": osrm, "foot": osrm, "cycling": osrm},
        use_database=False,
    )


def req(**kw):
    base = {"origin": {"lat": O[0], "lon": O[1]}, "destination": {"lat": D[0], "lon": D[1]}}
    base.update(kw)
    return RouteRequestV2(**base)


def plan(e, r):
    return asyncio.run(e.plan(r))


def test_reference_is_osrm_primary_and_duplicates_removed():
    primary = osrm_route(DIRECT)
    osrm = FakeOSRM([primary], corridor_routes=[osrm_route(DIRECT), osrm_route(EAST), osrm_route(EAST)])
    res = plan(engine(osrm), req())
    kinds = [r.origin_kind for r in res.routes]
    assert kinds.count("osrm_primary") == 1
    assert len(res.routes) == 2  # direct duplicate + repeated EAST removed
    ref = next(r for r in res.routes if r.is_reference)
    assert res.reference_route_id == ref.id
    assert ref.classification["type"] == "reference"


def test_impractical_detours_are_filtered():
    huge = via(O, (12.80, 77.40), D)
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(huge)])
    res = plan(engine(osrm), req())
    assert len(res.routes) == 1


def test_free_flow_basis_without_traffic_and_preference_fallback():
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(EAST)])
    res = plan(engine(osrm), req(preference="least_traffic_now"))
    assert res.comparison_basis == "free_flow"
    assert res.preference_applied.value == "fastest"
    assert "unavailable" in res.preference_note
    assert any("free-flow" in w for w in res.warnings)
    assert {s.name: s.status for s in res.data_sources}["tomtom_traffic"] == "not_configured"


def test_traffic_timing_changes_recommendation_to_longcut():
    # Direct route has heavy delay; the longer EAST corridor is faster with traffic.
    direct_km = round(osrm_route(DIRECT)["distance"] / 1000)
    east_km = round(osrm_route(EAST)["distance"] / 1000)
    tomtom = FakeTomTom(delay_by_length={direct_km: 1500.0, east_km: 30.0})
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(EAST)])
    res = plan(engine(osrm, tomtom), req())
    assert res.comparison_basis == "traffic_live"
    best = next(r for r in res.routes if r.recommended)
    assert best.origin_kind == "corridor"
    assert best.classification["type"] == "longcut"
    assert best.classification["basis"] == "traffic_live"
    assert best.traffic and best.traffic.source == "tomtom"
    assert any("Recommended" in line for line in best.explanation)


def test_mismatched_tomtom_reconstruction_is_rejected():
    tomtom = FakeTomTom(length_factor=1.3)  # TomTom route 30% longer = different road
    osrm = FakeOSRM([osrm_route(DIRECT)])
    res = plan(engine(osrm, tomtom), req())
    r = res.routes[0]
    assert r.traffic is None
    assert "rejected" in r.traffic_note
    assert res.comparison_basis == "free_flow"


def test_future_departure_uses_predicted_basis():
    tomtom = FakeTomTom()
    osrm = FakeOSRM([osrm_route(DIRECT)])
    res = plan(engine(osrm, tomtom), req(depart_at=(datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()))
    assert res.departure_mode == "future"
    assert res.comparison_basis == "traffic_predicted"


def test_walk_has_no_traffic_and_never_falls_back_to_car():
    osrm = FakeOSRM([osrm_route(DIRECT, speed_mps=1.4)])
    res = plan(engine(osrm, FakeTomTom()), req(vehicle="walk"))
    assert res.vehicle_profile["lua_profile"] == "foot.lua"
    assert {s.name: s.status for s in res.data_sources}["tomtom_traffic"] == "not_applicable"
    assert osrm.calls[0]["profile"] == "foot"

    no_foot = engine(FakeOSRM([osrm_route(DIRECT)]), osrm_foot_url=None)
    no_foot._clients.pop("foot")
    with pytest.raises(UpstreamUnavailable) as err:
        plan(no_foot, req(vehicle="walk"))
    assert err.value.code == "mode_unavailable"


def test_motorcycle_discloses_car_graph():
    res = plan(engine(FakeOSRM([osrm_route(DIRECT)])), req(vehicle="motorcycle"))
    assert res.vehicle_profile["profile_status"] == "car_graph_approximation"


def test_avoid_validation_and_passthrough():
    osrm = FakeOSRM([osrm_route(DIRECT)])
    plan(engine(osrm), req(avoid=["toll"]))
    assert osrm.calls[0]["exclude"] == ["toll"]
    with pytest.raises(AppError) as err:
        plan(engine(FakeOSRM([osrm_route(DIRECT)])), req(vehicle="bicycle", avoid=["toll"]))
    assert err.value.code == "unsupported_avoid"


def test_invalid_departures_and_same_place():
    e = engine(FakeOSRM([osrm_route(DIRECT)]))
    with pytest.raises(AppError):
        plan(e, req(depart_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()))
    with pytest.raises(AppError):
        plan(e, req(depart_at=(datetime.now(timezone.utc) + timedelta(days=9)).isoformat()))
    with pytest.raises(AppError):
        plan(e, req(destination={"lat": O[0], "lon": O[1]}))


def test_osrm_down_is_reported_as_upstream_unavailable():
    with pytest.raises(UpstreamUnavailable):
        plan(engine(FakeOSRM([], fail=True)), req())


def test_tomtom_failure_degrades_gracefully():
    tomtom = FakeTomTom(fail=RuntimeError("boom"))
    res = plan(engine(FakeOSRM([osrm_route(DIRECT)]), tomtom), req())
    assert res.routes and res.comparison_basis == "free_flow"
    assert {s.name: s.status for s in res.data_sources}["tomtom_traffic"] == "unavailable"


def test_corridors_scale_with_trip_length():
    short = corridor_waypoints(12.97, 77.59, 12.971, 77.591)
    assert short == []
    long = corridor_waypoints(*O, *D)
    assert len(long) == 10


class _Inc:
    def __init__(self, geometry=None, lat=0.0, lon=0.0):
        self.geometry, self.lat, self.lon = geometry, lat, lon


def test_incidents_must_run_along_the_route_not_cross_it():
    from routing.engine import incident_on_route
    from routing.geometry import PointIndex, resample

    route = straight((12.90, 77.60), (12.90, 77.62), n=50)  # east-west road
    index = PointIndex(resample(route, 10.0), cell_m=60.0)
    along = {"type": "LineString", "coordinates": straight((12.90, 77.605), (12.90, 77.607), n=10)}
    crossing = {"type": "LineString", "coordinates": straight((12.895, 77.61), (12.9001, 77.61), n=10)}  # side street touching it
    assert incident_on_route(_Inc(along), index)[0] is True
    assert incident_on_route(_Inc(crossing), index)[0] is False
    assert incident_on_route(_Inc(None, 12.90001, 77.611), index)[0] is True  # point on the road
    assert incident_on_route(_Inc(None, 12.9005, 77.611), index)[0] is False  # ~55 m away
