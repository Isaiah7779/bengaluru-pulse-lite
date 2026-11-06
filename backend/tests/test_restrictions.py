"""motorcycle=no and private-road detection on routes produced by the car graph."""

import pytest

from routing.restrictions import RestrictedWays, bypass_waypoints, motorcycle_restrictions

from fakes import straight

ROAD = straight((12.90, 77.40), (12.90, 77.45), n=200)  # ~5.4 km east-west, nodes every ~27 m


def ways(coords):
    return RestrictedWays(tag="motorcycle=no", source="test", ways=[{"osm_id": 1, "name": "X", "coordinates": coords}])


def test_exact_node_match_counts_route_length_on_the_way():
    r = ways(ROAD)
    on = ROAD[20:120]  # same OSM nodes, as OSRM overview=full returns them
    assert abs(r.used_length_m(on) - 99 * 27.0) < 200
    assert r.stretches(on) == [(0, 99)]


def test_parallel_service_road_is_not_flagged():
    r = ways(ROAD)
    service = straight((12.9003, 77.40), (12.9003, 77.45), n=150)  # ~33 m north, different nodes
    assert r.used_length_m(service) == 0.0


def test_crossing_or_touching_at_a_junction_is_not_flagged():
    r = ways(ROAD)
    crossing = straight((12.89, 77.42), (12.91, 77.42), n=60)
    assert r.used_length_m(crossing) == 0.0


def test_slightly_shifted_geometry_is_caught_by_the_near_match():
    r = ways(ROAD)
    shifted = straight((12.90002, 77.40), (12.90002, 77.45), n=137)  # ~2 m off, other node spacing
    assert r.used_length_m(shifted) > 4000


def test_bypass_points_sit_beside_the_restricted_stretch():
    vias = bypass_waypoints(ROAD, (50, 150))
    assert len(vias) == 4
    lats = sorted(v[0][0] for v in vias)
    assert lats[0] < 12.90 < lats[-1]  # both sides of an east-west road


def test_shipped_data_covers_the_mysuru_expressway():
    data = motorcycle_restrictions()
    assert data is not None and data.count > 100
    assert "Bengaluru-Mysuru Expressway" in data.names()
    assert "OpenStreetMap" in data.source


# --- Real OpenStreetMap samples (tests/fixtures/osm_restriction_samples.json) --------------------

import json
from pathlib import Path

from routing.access import access_restrictions, effective_access, segment_hash
from routing.geometry import line_length_m

SAMPLES = json.loads((Path(__file__).parent / "fixtures" / "osm_restriction_samples.json").read_text(encoding="utf-8"))


def _way(group, osm_id=None):
    return next(w for w in SAMPLES[group] if osm_id is None or w["osm_id"] == osm_id)


def test_real_mysuru_expressway_way_is_in_the_shipped_data_and_detected():
    way = _way("mysuru_expressway_motorcycle_no", 1154242636)
    assert way["tags"] == {"highway": "motorway", "name": "Bengaluru-Mysuru Expressway", "ref": "NH275",
                           "motorcycle": "no", "oneway": "yes"}
    data = motorcycle_restrictions()
    assert 1154242636 in {w["osm_id"] for w in data.ways}
    used = data.used_length_m(way["coordinates"])
    assert used == pytest.approx(line_length_m(way["coordinates"]), rel=0.01)


def test_real_service_roads_beside_the_expressway_are_not_flagged():
    data = motorcycle_restrictions()
    for way in SAMPLES["mysuru_parallel_public"]:
        assert way["tags"].get("motorcycle") != "no"
        assert data.used_length_m(way["coordinates"]) == 0.0


def test_real_goraguntepalya_flyover_is_detected():
    way = _way("goraguntepalya_flyover_motorcycle_no")
    assert way["tags"]["motorcycle"] == "no"
    assert motorcycle_restrictions().used_length_m(way["coordinates"]) > 0.9 * line_length_m(way["coordinates"])


def test_real_rmz_ecospace_private_roads_are_in_the_access_data():
    access = access_restrictions()
    assert access is not None and access.meta["ways"] > 40_000
    for way in SAMPLES["ecospace_private"]:
        coords = way["coordinates"]
        private = effective_access(way["tags"]) == "private"
        in_data = [segment_hash(a, b) in access for a, b in zip(coords, coords[1:])]
        assert all(in_data) if private else not any(in_data), way["osm_id"]
    # Chiguru Ecospace Mainroad (motor_vehicle=yes) is public for cars and must not be flagged.
    assert any(effective_access(w["tags"]) == "yes" for w in SAMPLES["ecospace_private"])


def test_public_outer_ring_road_next_to_ecospace_is_not_flagged():
    access = access_restrictions()
    orr = _way("orr_public_near_ecospace")
    assert orr["tags"]["name"] == "Outer Ring Road" and "access" not in orr["tags"]
    assert not any(access.flags(orr["coordinates"]))


def test_private_road_counts_only_mid_trip():
    access = access_restrictions()
    eco = _way("ecospace_private", 233028789)["coordinates"]
    orr = _way("orr_public_near_ecospace")["coordinates"]
    # through the campus: the whole private way (~72 m) counts, so the route is rejected
    assert access.through_m(orr + eco + orr) == pytest.approx(line_length_m(eco), rel=0.01)
    assert access.through_m(eco + orr) == 0.0  # trip starts inside the campus: the traveller's own origin
    assert access.through_m(orr + eco) == 0.0  # trip ends inside


def test_effective_access_follows_car_lua_tag_order():
    assert effective_access({"access": "private", "motor_vehicle": "yes"}) == "yes"
    assert effective_access({"access": "yes", "motorcar": "private"}) == "private"
    assert effective_access({"vehicle": "destination;delivery"}) == "destination"
    assert effective_access({}) is None
