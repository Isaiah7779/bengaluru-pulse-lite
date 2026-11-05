"""Address search via Photon: result shaping, outage/rate-limit errors, reverse geocoding.

Photon is replaced by an httpx MockTransport; the live check is test_geocode_live below
(marked integration, skipped offline).
"""

from __future__ import annotations

import os

import httpx
import pytest

from core.settings import get_settings
from geocoding import service


def feature(lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


CMRIT = feature(77.7115, 12.9662, osm_type="W", osm_id=122691466, osm_key="amenity", osm_value="college",
                name="CMR Institute of Technology", street="4th Cross Road", locality="AECS Layout A Block",
                district="Bharath Aikya Ward", county="Bangalore East", postcode="560037")
HOUSE = feature(77.7490, 12.9810, osm_type="N", osm_id=1, osm_key="place", osm_value="house",
                housenumber="367", street="6th Cross Road", locality="Whitefield", postcode="560066")
STREET = feature(77.7400, 12.9700, osm_type="W", osm_id=2, osm_key="highway", osm_value="primary",
                 name="Whitefield Main Road", district="Varthur", postcode="560066")
OUTSIDE = feature(72.87, 19.07, osm_type="N", osm_id=3, osm_key="place", osm_value="city", name="Mumbai")


@pytest.fixture
def photon(monkeypatch):
    """Route Photon calls to a handler the test sets; returns the list of requests made."""

    settings = get_settings()
    monkeypatch.setattr(settings, "geocode_fallback_enabled", True)
    monkeypatch.setattr(settings, "photon_url", "http://photon.test")
    service._PHOTON_CACHE.clear()
    service._PHOTON_STATE["backoff_until"] = 0.0
    state = {"handler": lambda req: httpx.Response(200, json={"features": []}), "requests": []}

    def transport(req):
        state["requests"].append(req)
        return state["handler"](req)

    monkeypatch.setattr(service, "async_client", lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(transport)))
    yield state
    service._PHOTON_CACHE.clear()
    service._PHOTON_STATE["backoff_until"] = 0.0


def test_search_returns_addresses_streets_and_pois_inside_bengaluru(client, photon):
    photon["handler"] = lambda req: httpx.Response(200, json={"features": [CMRIT, HOUSE, STREET, OUTSIDE]})
    r = client.get("/v1/geocode/search", params={"q": "whitefield", "limit": 7})
    assert r.status_code == 200
    body = r.json()
    by_name = {x["name"]: x for x in body["results"]}
    assert set(by_name) == {"CMR Institute of Technology", "367 6th Cross Road", "Whitefield Main Road"}
    assert by_name["367 6th Cross Road"]["category_label"] == "Address"
    assert by_name["367 6th Cross Road"]["label"] == "367 6th Cross Road, Whitefield, 560066"
    assert by_name["Whitefield Main Road"]["category_label"] == "Street"
    assert by_name["CMR Institute of Technology"]["label"].startswith("CMR Institute of Technology, 4th Cross Road, AECS Layout A Block")
    assert body["sources"] == ["photon"] and body["unavailable"] == []
    assert "Photon" in body["attribution"]
    params = photon["requests"][0].url.params
    assert params["bbox"] == "77.3,12.7,77.95,13.3" and params["lat"] and params["lon"]


def test_results_are_cached(client, photon):
    photon["handler"] = lambda req: httpx.Response(200, json={"features": [CMRIT]})
    for _ in range(3):
        assert client.get("/v1/geocode/search", params={"q": "cmr"}).json()["results"]
    assert len(photon["requests"]) == 1


def test_short_queries_do_not_call_photon(client, photon):
    r = client.get("/v1/geocode/search", params={"q": "cm"})
    assert r.status_code == 200 and r.json()["results"] == []
    assert photon["requests"] == []


def test_network_failure_is_503_not_no_match(client, photon):
    def down(req):
        raise httpx.ConnectError("boom", request=req)

    photon["handler"] = down
    r = client.get("/v1/geocode/search", params={"q": "cmr"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "geocoder_unavailable"


def test_http_error_is_503(client, photon):
    photon["handler"] = lambda req: httpx.Response(502, text="bad gateway")
    assert client.get("/v1/geocode/search", params={"q": "hoodi"}).json()["error"]["code"] == "geocoder_unavailable"


def test_rate_limit_is_reported_and_backs_off(client, photon):
    photon["handler"] = lambda req: httpx.Response(429)
    r = client.get("/v1/geocode/search", params={"q": "varthur"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "geocoder_rate_limited"
    client.get("/v1/geocode/search", params={"q": "hoodi"})
    assert len(photon["requests"]) == 1  # backing off: no second call to Photon


def test_genuine_no_match_is_empty_200(client, photon):
    r = client.get("/v1/geocode/search", params={"q": "zzqxv"})
    assert r.status_code == 200 and r.json()["results"] == [] and r.json()["unavailable"] == []


def test_reverse_uses_photon_address(client, photon):
    photon["handler"] = lambda req: httpx.Response(200, json={"features": [HOUSE]})
    rev = client.get("/v1/geocode/reverse", params={"lat": 12.9811, "lon": 77.7491}).json()
    assert rev["source"] == "photon" and rev["label"] == "367 6th Cross Road, Whitefield, 560066"
    assert rev["within_bengaluru"]


def test_reverse_falls_back_when_photon_is_down(client, photon):
    photon["handler"] = lambda req: httpx.Response(500)
    rev = client.get("/v1/geocode/reverse", params={"lat": 12.9811, "lon": 77.7491})
    assert rev.status_code == 200 and rev.json()["source"] == "openstreetmap"


def test_ready_reports_place_search(client, photon):
    photon["handler"] = lambda req: httpx.Response(503)
    body = client.get("/health/ready").json()
    assert body["checks"]["place_search"]["status"] == "down"


LIVE = ["CMR Institute of Technology Kundalahalli", "Marathahalli Bridge", "Hoodi", "Varthur",
        "Whitefield Main Road", "4th Cross Road Kundalahalli", "27th Main Road HSR Layout"]


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("PULSE_LIVE_GEOCODE"), reason="set PULSE_LIVE_GEOCODE=1 to query public Photon")
@pytest.mark.parametrize("q", LIVE)
def test_geocode_live(client, monkeypatch, q):
    settings = get_settings()
    monkeypatch.setattr(settings, "geocode_fallback_enabled", True)
    monkeypatch.setattr(settings, "photon_url", "https://photon.komoot.io")
    r = client.get("/v1/geocode/search", params={"q": q, "limit": 5})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results and all(service.in_bengaluru(x["lat"], x["lon"]) for x in results)
