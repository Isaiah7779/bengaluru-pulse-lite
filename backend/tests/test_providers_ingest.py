"""Provider parsing/validation, quota guard, secret redaction and ingestion."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pydantic import SecretStr

from core.log_config import RedactingFilter, redact
from core.settings import get_settings
from db.models import Incident, TrafficObservation, TrafficSegment
from db.session import session_scope
from providers import tomtom as tomtom_module
from providers.openmeteo import parse_current, parse_hourly
from providers.quota import QuotaGuard
from providers.tomtom import (
    FlowReading,
    IncidentReading,
    ProviderError,
    ProviderUnavailable,
    TomTomProvider,
    parse_flow,
    parse_incidents,
)
from traffic.ingest import ensure_segments, store_flow, store_incidents, store_weather
from traffic.state_engine import congestion_level, latest_segment_state


def flow_payload(**over):
    data = {"frc": "FRC2", "currentSpeed": 20, "freeFlowSpeed": 40, "currentTravelTime": 100, "freeFlowTravelTime": 50,
            "confidence": 0.95, "roadClosure": False,
            "coordinates": {"coordinate": [{"latitude": 12.9, "longitude": 77.6}, {"latitude": 12.91, "longitude": 77.61}]}}
    data.update(over)
    return {"flowSegmentData": data}


def test_parse_flow_valid_and_invalid():
    r = parse_flow(flow_payload())
    assert r.speed_ratio == 0.5 and r.geometry == [[77.6, 12.9], [77.61, 12.91]]
    for bad in ({"freeFlowSpeed": 0}, {"currentSpeed": -1}, {"currentSpeed": 400}, {"currentSpeed": 0}):
        with pytest.raises(ProviderError):
            parse_flow(flow_payload(**bad))
    assert parse_flow(flow_payload(currentSpeed=0, roadClosure=True)).road_closure
    with pytest.raises(ProviderError):
        parse_flow({"unexpected": 1})
    assert parse_flow(flow_payload(confidence=7)).confidence is None


def test_parse_incidents_skips_unusable_records():
    payload = {"incidents": [
        {"geometry": {"type": "Point", "coordinates": [77.6, 12.9]},
         "properties": {"id": "a", "iconCategory": 8, "magnitudeOfDelay": 4, "events": [{"description": "Closed"}], "from": "X", "to": "Y"}},
        {"geometry": {"type": "LineString", "coordinates": [[77.6, 12.9], [77.7, 13.0], [77.8, 13.1]]},
         "properties": {"id": "b", "iconCategory": 6, "magnitudeOfDelay": 2, "delay": 120}},
        {"geometry": {}, "properties": {"id": "c"}},  # no location
        {"geometry": {"type": "Point", "coordinates": [77.6, 12.9]}, "properties": {}},  # no id
    ]}
    rows = parse_incidents(payload)
    assert [r.external_id for r in rows] == ["a", "b"]
    assert rows[0].category == "road_closed" and rows[1].lat == 13.0 and rows[1].delay_s == 120


def test_open_meteo_parsing_converts_local_time_to_utc():
    payload = {"utc_offset_seconds": 19800, "current": {"time": "2026-10-22T08:30", "temperature_2m": 24.0, "weather_code": 61, "precipitation": 1.2}}
    r = parse_current(payload)
    assert r.observed_at == datetime(2026, 10, 22, 3, 0, tzinfo=timezone.utc)
    assert r.is_wet and r.description == "Slight rain"
    with pytest.raises(ProviderError):
        parse_current({"current": {"time": "2026-10-22T08:30", "temperature_2m": 80}})
    hourly = parse_hourly({"utc_offset_seconds": 0, "hourly": {"time": ["2026-10-22T10:00"], "temperature_2m": [25]}})
    assert hourly[0].temperature_c == 25


def test_redaction_of_keys_in_text_and_logs(caplog):
    url = "https://api.tomtom.com/x?point=1,2&key=SECRET123&unit=KMPH"
    assert "SECRET123" not in redact(url)
    record = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed %s", (url,), None)
    RedactingFilter().filter(record)
    assert "SECRET123" not in record.getMessage()
    assert "SECRET123" not in repr(get_settings().model_copy(update={"tomtom_api_key": SecretStr("SECRET123")}))


def test_tomtom_errors_never_contain_the_key(monkeypatch):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    def fake_client(timeout):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)

    monkeypatch.setattr(tomtom_module, "async_client", fake_client)
    provider = TomTomProvider(get_settings().model_copy(update={"tomtom_api_key": SecretStr("SUPERSECRETKEY")}))
    with pytest.raises(ProviderError) as err:
        asyncio.run(provider.flow_segment(12.9, 77.6))
    assert "SUPERSECRETKEY" not in str(err.value)
    assert "ConnectError" in str(err.value)


def test_tomtom_http_403_is_unavailable(monkeypatch):
    monkeypatch.setattr(tomtom_module, "async_client",
                        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={})), timeout=timeout))
    provider = TomTomProvider(get_settings().model_copy(update={"tomtom_api_key": SecretStr("k")}))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.flow_segment(12.9, 77.6))


def test_quota_guard_blocks_background_before_interactive():
    guard = QuotaGuard("tomtom", daily_budget=3, background_reserve=2)
    guard.acquire("flow", "collector", background=True)
    with pytest.raises(Exception):
        guard.acquire("flow", "collector", background=True)  # reserve kept for users
    guard.acquire("routing", "route_eval")
    guard.acquire("routing", "route_eval")
    with pytest.raises(Exception):
        guard.acquire("routing", "route_eval")
    assert guard.used_today() == 3


def reading(ts, speed=20.0):
    return FlowReading(speed, 40.0, None, None, 0.9, False, "FRC2", [[77.6, 12.9], [77.61, 12.91]], ts)


def test_flow_dedup_and_staleness():
    # Pin to second 5 of the current minute so +20 s stays in the same minute bucket.
    now = datetime.now(timezone.utc).replace(second=5, microsecond=0)
    with session_scope() as s:
        segs = ensure_segments(s)
        assert len(segs) == 26
        assert store_flow(s, segs[0], reading(now)) is True
        assert store_flow(s, segs[0], reading(now + timedelta(seconds=20))) is False  # same minute bucket
        assert store_flow(s, segs[1], reading(now - timedelta(hours=5))) is True
    with session_scope() as s:
        assert s.query(TrafficObservation).count() == 2
        state = {x["code"]: x for x in latest_segment_state(s, stale_minutes=90)}
    first, second = list(state.values())[:2]
    assert first["status"] == "fresh" and first["observation"]["congestion"] == "HEAVY"
    assert second["status"] == "stale"
    assert list(state.values())[2]["status"] == "no_data"


def test_incident_sweep_upserts_and_deactivates():
    def inc(i):
        return IncidentReading(i, "jam", 2, None, "A", "B", 12.9, 77.6, None, 60.0, None, None)

    with session_scope() as s:
        assert store_incidents(s, [inc("1"), inc("2")]) == {"created": 2, "updated": 0, "deactivated": 0}
    with session_scope() as s:
        result = store_incidents(s, [inc("2"), inc("3")])
        assert result == {"created": 1, "updated": 1, "deactivated": 1}
    with session_scope() as s:
        active = {i.external_id for i in s.query(Incident).filter_by(active=True)}
        assert active == {"2", "3"}


def test_congestion_levels():
    assert congestion_level(0.9) == "FREE"
    assert congestion_level(0.7) == "MODERATE"
    assert congestion_level(0.5) == "HEAVY"
    assert congestion_level(0.2) == "SEVERE"
    assert congestion_level(0.9, road_closure=True) == "CLOSED"


def test_collector_flow_with_fake_provider():
    from traffic.collector import collect_flow

    class Fake:
        configured = True
        calls = 0

        async def flow_segment(self, lat, lon, purpose, background):
            Fake.calls += 1
            if Fake.calls == 2:
                raise ProviderError("bad data")
            if Fake.calls == 5:
                raise ProviderUnavailable("budget exhausted")
            return reading(datetime.now(timezone.utc))

    stats = asyncio.run(collect_flow(get_settings(), Fake()))
    assert stats == {"stored": 3, "duplicate": 0, "invalid": 1, "skipped": 1}


def test_retention_job_removes_expired_personal_and_observation_data():
    from db.models import Trip, User
    from traffic.maintenance import run_retention

    settings = get_settings()
    old = datetime.now(timezone.utc) - timedelta(days=settings.retention_trip_days + 5)
    with session_scope() as s:
        u = User(email="r@example.com", password_hash="x", display_name="R")
        s.add(u)
        s.flush()
        s.add(Trip(user_id=u.id, origin_lat=1, origin_lon=1, destination_lat=2, destination_lon=2, vehicle="car", preference="fastest", created_at=old))
        s.add(Trip(user_id=u.id, origin_lat=1, origin_lon=1, destination_lat=2, destination_lon=2, vehicle="car", preference="fastest"))
        seg = ensure_segments(s)[0]
        store_flow(s, seg, reading(datetime.now(timezone.utc) - timedelta(days=settings.retention_observation_days + 1)))
    result = run_retention(settings)
    assert result["trips"] == 1 and result["traffic_observations"] == 1
    with session_scope() as s:
        assert s.query(Trip).count() == 1
