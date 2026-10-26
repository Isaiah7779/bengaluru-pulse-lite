"""Integration tests against live local services.

    pytest -m integration

Requires the Docker Compose stack (OSRM car/foot/bicycle on 5000-5002, PostGIS
on 5433). Skipped automatically when unreachable. No TomTom calls are made.
"""

import asyncio
import os
import subprocess
import sys
import uuid

import httpx
import pytest

from core.settings import get_settings
from routing.engine import RoutingEngine
from routing.osrm_client import OSRMClient
from routing.schemas import RouteRequestV2

from fakes import NullWeather

pytestmark = pytest.mark.integration

LIVE = {
    "driving": os.getenv("LIVE_OSRM_CAR", "http://localhost:5000"),
    "foot": os.getenv("LIVE_OSRM_FOOT", "http://localhost:5001"),
    "cycling": os.getenv("LIVE_OSRM_BICYCLE", "http://localhost:5002"),
}
PG_ADMIN_URL = os.getenv("LIVE_PG_URL", "postgresql://pulse:pulse_dev_only@127.0.0.1:5433/pulse")


def reachable(url: str) -> bool:
    try:
        return httpx.get(f"{url}/nearest/v1/x/77.5946,12.9716", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


requires_osrm = pytest.mark.skipif(not all(reachable(u) for u in LIVE.values()), reason="live OSRM not running")

PLACES = {
    "whitefield": (12.9698, 77.7500),
    "marathahalli": (12.9591, 77.7011),
    "electronic_city": (12.8456, 77.6603),
    "indiranagar": (12.9784, 77.6408),
    "yeshwanthpur": (13.0280, 77.5400),
    "airport": (13.1989, 77.7068),
    "koramangala": (12.9352, 77.6245),
    "hebbal": (13.0358, 77.5970),
}
BENCHMARKS = [
    ("whitefield", "marathahalli", 5, 12),
    ("whitefield", "electronic_city", 18, 35),
    ("indiranagar", "yeshwanthpur", 10, 22),
    ("airport", "whitefield", 30, 50),
    ("koramangala", "hebbal", 11, 22),
]


class NoTraffic:
    configured = False


def live_engine():
    settings = get_settings().model_copy(update={"osrm_url": LIVE["driving"], "osrm_foot_url": LIVE["foot"], "osrm_bicycle_url": LIVE["cycling"]})
    clients = {k: OSRMClient(v) for k, v in LIVE.items()}
    return RoutingEngine(settings, tomtom=NoTraffic(), weather=NullWeather(), clients=clients, use_database=False)


@requires_osrm
@pytest.mark.parametrize("origin,destination,min_km,max_km", BENCHMARKS)
def test_benchmark_trip(origin, destination, min_km, max_km):
    o, d = PLACES[origin], PLACES[destination]
    res = asyncio.run(live_engine().plan(RouteRequestV2(
        origin={"lat": o[0], "lon": o[1]}, destination={"lat": d[0], "lon": d[1]}, vehicle="car", max_routes=5)))
    ref = next(r for r in res.routes if r.is_reference)
    assert min_km <= ref.distance_m / 1000 <= max_km
    assert ref.steps and ref.steps[-1].instruction.startswith("Arrive")
    assert len(ref.geometry["coordinates"]) > 20
    for r in res.routes:
        assert r.distance_m > 0 and r.eta_s > 0
        assert r.classification["type"] in {"reference", "shortcut", "longcut", "alternative"}
    # Geometry-aware dedup: no two returned routes are near-identical.
    from routing.geometry import route_similarity

    coords = [r.geometry["coordinates"] for r in res.routes]
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            assert route_similarity(coords[i], coords[j]) < 0.85


@requires_osrm
def test_modes_use_distinct_graphs():
    o, d = PLACES["indiranagar"], PLACES["yeshwanthpur"]
    results = {}
    for vehicle in ("car", "walk", "bicycle"):
        res = asyncio.run(live_engine().plan(RouteRequestV2(
            origin={"lat": o[0], "lon": o[1]}, destination={"lat": d[0], "lon": d[1]}, vehicle=vehicle, max_routes=1)))
        results[vehicle] = res.routes[0]
    speeds = {v: r.distance_m / r.free_flow_duration_s * 3.6 for v, r in results.items()}
    assert 3 <= speeds["walk"] <= 6.5
    assert 8 <= speeds["bicycle"] <= 25
    assert speeds["car"] > 25


@requires_osrm
def test_avoid_toll_changes_nice_road_trip():
    o, d = (12.8456, 77.6603), (12.9080, 77.4870)
    base = asyncio.run(live_engine().plan(RouteRequestV2(origin={"lat": o[0], "lon": o[1]}, destination={"lat": d[0], "lon": d[1]}, max_routes=1)))
    avoid = asyncio.run(live_engine().plan(RouteRequestV2(origin={"lat": o[0], "lon": o[1]}, destination={"lat": d[0], "lon": d[1]}, max_routes=1, avoid=["toll"])))
    assert "NICE" in base.routes[0].summary
    assert "NICE" not in avoid.routes[0].summary


def pg_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(PG_ADMIN_URL, connect_timeout=2):
            return True
    except Exception:
        return False


@pytest.mark.skipif(not pg_available(), reason="live PostGIS not running")
def test_alembic_migrations_on_fresh_postgis_database():
    import psycopg

    name = f"pulse_migtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    url = PG_ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    env = {**os.environ, "DATABASE_URL": url}
    backend = os.path.dirname(os.path.dirname(__file__))
    try:
        for args in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
            out = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env, capture_output=True, text=True)
            assert out.returncode == 0, out.stderr[-2000:]
        with psycopg.connect(url) as conn:
            indexes = {r[0] for r in conn.execute("select indexname from pg_indexes where schemaname='public'")}
        assert "ix_places_name_trgm" in indexes and "ix_incidents_geog" in indexes
    finally:
        with psycopg.connect(PG_ADMIN_URL, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
