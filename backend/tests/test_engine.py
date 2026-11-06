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


def test_avoid_disabled_for_servers_without_exclude():
    from routing.route_profiles import get_vehicle_metadata

    settings = get_settings().model_copy(update={"osrm_exclude_supported": False})
    assert get_vehicle_metadata("car", settings)["avoid_options"] == []
    osrm = FakeOSRM([osrm_route(DIRECT)])
    with pytest.raises(AppError) as err:
        plan(engine(osrm, osrm_exclude_supported=False), req(avoid=["toll"]))
    assert err.value.code == "unsupported_avoid"
    assert not osrm.calls
    plan(engine(osrm, osrm_exclude_supported=False), req())
    assert not osrm.calls[0]["exclude"]


def test_corridor_requests_can_be_capped_for_public_servers():
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(EAST)] * 10)
    plan(engine(osrm, osrm_corridor_max=3, osrm_extra_candidates_max=0, osrm_max_concurrency=1), req())
    assert len(osrm.calls) == 1 + 3


def test_extra_candidate_budget_adds_direct_and_detour_requests():
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(EAST)] * 12)
    res = plan(engine(osrm, osrm_corridor_max=2, osrm_extra_candidates_max=4, osrm_max_concurrency=1), req())
    assert len(osrm.calls) == 1 + 2 + 4
    assert res.selection.osrm_requests == 7
    # The first extra request is a single via-point on the straight origin-destination line.
    mid = osrm.calls[3]["points"][1]
    assert mid == pytest.approx(((O[0] + D[0]) / 2, (O[1] + D[1]) / 2))


def bump(a, b, start=0.45, end=0.55, offset_deg=0.003):
    """Straight line a->b with a short sideways bump in the middle (a near-duplicate)."""

    p = lambda f, off=0.0: (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f + off)
    pts = [p(0), p(start), p(start, offset_deg), p(end, offset_deg), p(end), p(1)]
    coords = []
    for x, y in zip(pts, pts[1:]):
        coords.extend(straight(x, y, n=12)[:-1])
    coords.append([pts[-1][1], pts[-1][0]])
    return coords


def spurred(a, m, b, spur_end):
    """a -> m, out to a dead end and back to m, then m -> b."""

    return straight(a, m, 30)[:-1] + straight(m, spur_end, 15)[:-1] + straight(spur_end, m, 15)[:-1] + straight(m, b, 30)


def test_spurred_via_routes_are_rerouted_through_the_spur_entry():
    m = (12.985, 77.6650)
    spur = osrm_route(spurred(O, m, D, (12.985, 77.6700)))  # ~540 m dead-end excursion
    repaired = osrm_route(EAST)
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[spur, repaired])
    res = plan(engine(osrm, osrm_corridor_max=1, osrm_extra_candidates_max=0, osrm_spur_repair_max=1), req())
    assert len(osrm.calls) == 3 and res.selection.osrm_requests == 3
    entry = osrm.calls[2]["points"][1]
    assert entry == pytest.approx(m, abs=0.001)  # re-routed through the point the spur left from
    assert len(res.routes) == 2
    assert res.selection.rejected.get("u_turn_spur") == 1

    no_repair = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[spur, repaired])
    res = plan(engine(no_repair, osrm_corridor_max=1, osrm_extra_candidates_max=0, osrm_spur_repair_max=0), req())
    assert len(no_repair.calls) == 2 and len(res.routes) == 1


def _with_classes(route, classes_by_step):
    steps = [
        {"name": f"s{i}", "distance": dist, "duration": dist / 10, "maneuver": {"type": "turn"},
         "intersections": [{"classes": classes}]}
        for i, (dist, classes) in enumerate(classes_by_step)
    ]
    return {**route, "legs": [{"steps": steps}]}


def test_routes_through_private_roads_mid_trip_are_rejected():
    from routing.engine import restricted_through_m

    mid = _with_classes(osrm_route(EAST), [(4000, []), (800, ["restricted"]), (5000, [])])
    ends = _with_classes(osrm_route(EAST), [(120, ["restricted"]), (9000, []), (60, ["restricted"])])
    assert restricted_through_m(mid) == 800
    assert restricted_through_m(ends) == 0  # starting or ending inside a gated area is the user's own trip
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[mid])
    res = plan(engine(osrm, osrm_corridor_max=1, osrm_extra_candidates_max=0), req())
    assert len(res.routes) == 1
    assert res.selection.rejected == {"restricted_access": 1}
    assert "private or destination-only" in res.selection.note


def test_near_duplicates_are_removed_by_shared_length():
    near = bump(O, D)  # ~90% of its length on DIRECT
    osrm = FakeOSRM([osrm_route(DIRECT), osrm_route(near)], corridor_routes=[osrm_route(EAST)])
    res = plan(engine(osrm, osrm_extra_candidates_max=0), req())
    assert len(res.routes) == 2
    assert res.selection.rejected.get("near_duplicate", 0) >= 1
    assert all(r.shared_max_pct is not None and r.shared_max_pct <= 70 for r in res.routes)


def test_shortest_distance_route_is_kept_and_labelled_beside_fastest():
    # Reference is fast but long; a direct route is shorter but slower.
    fast_long = osrm_route(EAST, duration=900.0)
    short_slow = osrm_route(DIRECT, duration=1200.0)
    osrm = FakeOSRM([fast_long], corridor_routes=[short_slow])
    res = plan(engine(osrm, osrm_extra_candidates_max=0), req())
    by_label = {label: r for r in res.routes for label in r.labels}
    assert by_label["fastest"].is_reference
    assert by_label["shortest_distance"].distance_m < by_label["fastest"].distance_m
    assert any("not a guaranteed shortest path" in line for line in by_label["shortest_distance"].explanation)
    shortest_first = plan(engine(FakeOSRM([fast_long], corridor_routes=[short_slow]), osrm_extra_candidates_max=0),
                          req(preference="shortest"))
    assert "shortest_distance" in shortest_first.routes[0].labels


def test_single_route_is_reported_honestly():
    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(DIRECT), osrm_route(bump(O, D))])
    res = plan(engine(osrm, osrm_extra_candidates_max=0), req())
    assert len(res.routes) == 1
    assert res.selection.returned == 1
    assert res.selection.rejected["near_duplicate"] == 2
    note = res.selection.note
    assert note and "Only one distinct" in note and note in res.warnings
    assert res.routes[0].labels == ["fastest", "shortest_distance"]


def _osm_samples():
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "fixtures" / "osm_restriction_samples.json").read_text(encoding="utf-8"))


def _shifted(coords, dlon=0.0006, dlat=0.0006):
    """A test geometry ~90 m beside a real way (not an OSM road; used as the legal alternative)."""

    return [[lon + dlon, lat + dlat] for lon, lat in coords]


def _req_along(coords, **kw):
    (lon1, lat1), (lon2, lat2) = coords[0], coords[-1]
    return req(origin={"lat": lat1, "lon": lon1}, destination={"lat": lat2, "lon": lon2}, **kw)


def test_motorcycle_routes_on_the_real_mysuru_expressway_are_removed():
    # Real OSM way 1154242636: highway=motorway, name=Bengaluru-Mysuru Expressway, motorcycle=no.
    way = _osm_samples()["mysuru_expressway_motorcycle_no"][0]
    assert way["tags"]["motorcycle"] == "no" and way["tags"]["name"] == "Bengaluru-Mysuru Expressway"
    expressway = way["coordinates"]
    beside = _shifted(expressway)
    osrm = FakeOSRM([osrm_route(expressway)], corridor_routes=[osrm_route(beside)])
    res = plan(engine(osrm, osrm_extra_candidates_max=0, osrm_spur_repair_max=0), _req_along(expressway, vehicle="motorcycle"))
    assert len(res.routes) == 1 and res.routes[0].origin_kind == "corridor"
    assert res.routes[0].is_reference and res.routes[0].classification["type"] == "reference"
    assert res.selection.rejected["motorcycle_restricted"] == 1
    assert any("closed to motorcycles" in w and "Bengaluru-Mysuru Expressway" in w for w in res.warnings)
    assert "avoids roads closed" in res.reference_description
    assert {s.name: s.status for s in res.data_sources}["motorcycle_restrictions"] == "ok"
    # Cars may legally use the expressway: the same geometry stays the reference for car.
    car = plan(engine(FakeOSRM([osrm_route(expressway)], corridor_routes=[osrm_route(beside)]),
                      osrm_extra_candidates_max=0, osrm_spur_repair_max=0), _req_along(expressway))
    assert any(r.origin_kind == "osrm_primary" and r.is_reference for r in car.routes)


def test_motorcycle_on_real_expressway_tries_bypasses_then_refuses():
    expressway = _osm_samples()["mysuru_expressway_motorcycle_no"][0]["coordinates"]
    beside = _shifted(expressway)
    # Every first-round candidate is the expressway; a bypass via-point finds the road beside it.
    osrm = FakeOSRM([osrm_route(expressway)], corridor_routes=[osrm_route(expressway)] * 2 + [osrm_route(beside)])
    res = plan(engine(osrm, osrm_corridor_max=2, osrm_extra_candidates_max=0, osrm_spur_repair_max=0),
               _req_along(expressway, vehicle="motorcycle"))
    assert any(call["exclude"] == ["motorway"] for call in osrm.calls)  # own-server retry without motorways
    assert res.routes[0].origin_kind == "bypass"

    stuck = FakeOSRM([osrm_route(expressway)], corridor_routes=[osrm_route(expressway)] * 20)
    with pytest.raises(AppError) as err:
        plan(engine(stuck, osrm_corridor_max=2, osrm_extra_candidates_max=0, osrm_spur_repair_max=0),
             _req_along(expressway, vehicle="motorcycle"))
    assert err.value.code == "no_legal_route" and err.value.status_code == 422


def test_route_through_real_rmz_ecospace_private_roads_is_rejected_without_osrm_classes():
    # Real OSM way 233028789: highway=unclassified, name=Ecospace Internal Road, access=private.
    samples = _osm_samples()
    eco = next(w for w in samples["ecospace_private"] if w["osm_id"] == 233028789)
    assert eco["tags"]["access"] == "private"
    inside = eco["coordinates"]
    start, end = (inside[0][1] - 0.02, inside[0][0] - 0.02), (inside[-1][1] + 0.02, inside[-1][0] + 0.02)
    through = straight(start, (inside[0][1], inside[0][0]), 20)[:-1] + inside + straight((inside[-1][1], inside[-1][0]), end, 20)[1:]
    direct = straight(start, end)
    # No "classes" on any step, exactly like the public FOSSGIS server.
    osrm = FakeOSRM([osrm_route(direct)], corridor_routes=[osrm_route(through)])
    r = req(origin={"lat": start[0], "lon": start[1]}, destination={"lat": end[0], "lon": end[1]})
    res = plan(engine(osrm, osrm_corridor_max=1, osrm_extra_candidates_max=0, osrm_spur_repair_max=0), r)
    assert len(res.routes) == 1 and res.routes[0].origin_kind == "osrm_primary"
    assert res.selection.rejected == {"restricted_access": 1}
    check = {s.name: s for s in res.data_sources}["private_road_check"]
    assert check.status == "ok" and "returns no road classes" in check.detail


def test_deadline_returns_partial_results_and_cancels_slow_alternatives():
    import time as _time

    osrm = FakeOSRM([osrm_route(DIRECT)], corridor_routes=[osrm_route(EAST)] * 10, via_delay_s=0.2)
    e = engine(osrm, osrm_corridor_max=10, osrm_extra_candidates_max=0, osrm_spur_repair_max=0,
               osrm_max_concurrency=1, route_plan_deadline_s=0.5)
    t0 = _time.monotonic()
    res = plan(e, req())
    elapsed = _time.monotonic() - t0
    assert elapsed < 1.5  # 10 sequential 0.2 s calls would take 2 s
    assert res.selection.rejected["timed_out"] >= 5  # cancelled before finishing
    assert osrm.completed < 1 + 10
    assert len(res.routes) == 2  # primary + the corridor that finished in time
    assert any("planning limit" in w for w in res.warnings)


def test_deadline_without_a_primary_route_is_a_retryable_503():
    import time as _time

    osrm = FakeOSRM([osrm_route(DIRECT)], primary_delay_s=5.0)
    t0 = _time.monotonic()
    with pytest.raises(UpstreamUnavailable) as err:
        plan(engine(osrm, route_plan_deadline_s=0.3), req())
    assert _time.monotonic() - t0 < 1.5
    assert err.value.code == "routing_deadline_exceeded" and err.value.status_code == 503
    assert "try again" in err.value.message


def test_motorcycle_bypass_shares_the_deadline():
    import time as _time

    expressway = _osm_samples()["mysuru_expressway_motorcycle_no"][0]["coordinates"]
    osrm = FakeOSRM([osrm_route(expressway)], corridor_routes=[osrm_route(_shifted(expressway))] * 10, via_delay_s=5.0)
    t0 = _time.monotonic()
    with pytest.raises(UpstreamUnavailable) as err:  # only the illegal primary arrived in time
        plan(engine(osrm, osrm_corridor_max=2, osrm_extra_candidates_max=0, route_plan_deadline_s=0.4),
             _req_along(expressway, vehicle="motorcycle"))
    assert _time.monotonic() - t0 < 2.0
    assert err.value.code == "routing_deadline_exceeded"


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


def test_osrm_circuit_breaker_fails_fast_after_connection_failure(monkeypatch):
    import time as _time

    import httpx

    from routing import osrm_client
    from routing.osrm_client import OSRMClient, OSRMError

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        raise httpx.ConnectError("refused", request=request)

    monkeypatch.setattr(osrm_client, "async_client", lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout))
    client = OSRMClient("http://osrm-dead.test")
    with pytest.raises(OSRMError):
        asyncio.run(client.nearest(12.97, 77.59))
    start = _time.monotonic()
    with pytest.raises(OSRMError, match="recent connection failure"):
        asyncio.run(client.nearest(12.97, 77.59))
    assert calls["n"] == 1 and _time.monotonic() - start < 0.1
    assert asyncio.run(client.health()) is False
