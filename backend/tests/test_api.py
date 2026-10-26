"""API surface: health, legacy endpoints, geocoding, routing endpoint wiring."""

import pytest

from api import routing_api
from db.models import Place
from db.session import session_scope
from geocoding.service import parse_coordinates
from geocoding.text import normalize


def test_health_is_dependency_free(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "x-request-id" in r.headers


def test_ready_reports_osrm_down(client):
    r = client.get("/health/ready")
    assert r.status_code == 503  # fake OSRM hosts are unreachable in tests
    body = r.json()
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["osrm_car"]["status"] == "down"
    assert body["checks"]["tomtom"]["status"] == "not_configured"


@pytest.mark.parametrize("path,method", [("/forecast", "post"), ("/analytics", "get"), ("/historical-trends", "get"), ("/commute-advisor", "post")])
def test_simulated_endpoints_are_gone(client, path, method):
    r = client.request(method.upper(), path, json={} if method == "post" else None)
    assert r.status_code == 410
    assert "simulated" in r.json()["error"]["message"]


def test_hotspots_and_incidents_are_empty_not_fabricated(client):
    hot = client.get("/hotspots").json()
    assert hot["hotspots"] == [] and hot["worst_location"] is None
    inc = client.get("/incidents").json()
    assert inc["incidents"] == [] and inc["status"] == "no_data"


def test_legacy_predict_is_labelled(client):
    r = client.post("/predict", json={"location": "Silk Board", "traffic_volume": 250, "average_speed": 15, "weather": "Sunny"})
    assert r.status_code == 200
    assert r.json()["legacy"] is True and "Not a forecast" in r.json()["notice"]


def test_validation_errors_have_stable_shape(client):
    r = client.post("/v1/routes", json={"origin": {"lat": 200, "lon": 0}})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_unknown_route_404_shape(client):
    r = client.get("/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "http_404"


def test_coordinate_parsing():
    assert parse_coordinates("12.9716, 77.5946") == (12.9716, 77.5946)
    assert parse_coordinates("77.5946,12.9716") == (12.9716, 77.5946)  # lon,lat order corrected
    lat, lon = parse_coordinates("12°58'17.8\"N 77°35'40.6\"E")
    assert abs(lat - 12.9716) < 0.001 and abs(lon - 77.5946) < 0.001
    assert parse_coordinates("Indiranagar") is None


def test_normalize_expands_abbreviations():
    assert normalize("MG Rd., Bangalore") == "mg road bengaluru"


def seed_places():
    rows = [
        ("n", 1, "Indiranagar", "locality", "suburb", None, 12.9784, 77.6408, 0.8),
        ("n", 2, "Indiranagar Metro Station", "transit", "metro", "Indiranagar", 12.9783, 77.6387, 0.75),
        ("w", 3, "100 Feet Road", "street", "primary", "Indiranagar", 12.9720, 77.6410, 0.5),
        ("n", 4, "Indira Canteen", "poi", "restaurant", "Jayanagar", 12.9250, 77.5830, 0.3),
    ]
    with session_scope() as s:
        for t, i, name, cat, sub, loc, lat, lon, imp in rows:
            s.add(Place(osm_type=t, osm_id=i, name=name, name_normalized=normalize(name), category=cat,
                        subcategory=sub, locality=loc, lat=lat, lon=lon, importance=imp))


def test_geocode_search_and_reverse(client):
    seed_places()
    r = client.get("/v1/geocode/search", params={"q": "indiranagar"}).json()
    names = [x["name"] for x in r["results"]]
    assert names[0] == "Indiranagar" and "Indiranagar Metro Station" in names
    assert "Indira Canteen" not in names  # 'indiranagar' is not a prefix of 'indira canteen' tokens
    prefix = client.get("/v1/geocode/search", params={"q": "indi met"}).json()["results"]
    assert prefix[0]["name"] == "Indiranagar Metro Station"
    coord = client.get("/v1/geocode/search", params={"q": "12.97,77.64"}).json()["results"][0]
    assert coord["category"] == "coordinates" and coord["within_bengaluru"]
    rev = client.get("/v1/geocode/reverse", params={"lat": 12.97205, "lon": 77.64105}).json()
    assert rev["name"] == "100 Feet Road" and rev["locality"] == "Indiranagar"


def test_route_endpoint_saves_trip_only_for_signed_in_users(client, app, user_headers):
    from fakes import FakeOSRM, NullWeather, osrm_route, straight
    from core.settings import get_settings
    from routing.engine import RoutingEngine

    class NoTraffic:
        configured = False

    osrm = FakeOSRM([osrm_route(straight((12.97, 77.59), (12.93, 77.62)))])
    eng = RoutingEngine(get_settings(), tomtom=NoTraffic(), weather=NullWeather(), clients={"driving": osrm}, use_database=False)
    app.dependency_overrides[routing_api.get_engine] = lambda: eng
    try:
        body = {"origin": {"lat": 12.97, "lon": 77.59, "label": "A"}, "destination": {"lat": 12.93, "lon": 77.62, "label": "B"}, "save_trip": True}
        assert client.post("/v1/routes", json=body).status_code == 401
        r = client.post("/v1/routes", json=body, headers=user_headers)
        assert r.status_code == 200, r.text
        assert r.json()["trip_id"]
        trips = client.get("/v1/me/trips", headers=user_headers).json()
        assert trips[0]["origin_label"] == "A" and trips[0]["chosen_route"]["eta_basis"] == "free_flow"
        legacy = client.post("/routing/route", json={"origin": {"lat": 12.97, "lon": 77.59}, "destination": {"lat": 12.93, "lon": 77.62}})
        assert legacy.status_code == 200 and legacy.json()["routes"][0]["route_type"] == "regular"
    finally:
        app.dependency_overrides.clear()


def test_incident_report_requires_moderation(client, user_headers, admin_headers):
    r = client.post("/v1/incidents/report", headers=user_headers,
                    json={"category": "flooding", "description": "Underpass flooded", "lat": 12.97, "lon": 77.6})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    assert client.get("/v1/incidents").json()["incidents"] == []  # not public yet
    pending = client.get("/v1/admin/incidents/pending", headers=admin_headers).json()["incidents"]
    assert len(pending) == 1
    client.post(f"/v1/admin/incidents/{pending[0]['id']}/decision", headers=admin_headers, json={"decision": "publish"})
    assert len(client.get("/v1/incidents").json()["incidents"]) == 1
