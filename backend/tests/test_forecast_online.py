"""Prospective forecast logging and prediction-vs-actual evaluation.

Observations here are SYNTHETIC TEST FIXTURES created in-test; they are never
reported as results.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from db.models import PredictionRecord, TrafficObservation, TrafficSegment
from db.session import session_scope
from forecasting import online
from forecasting.online import baseline_predictions, bucket, log_forecasts, report, resolve_actuals, run_cycle

T0 = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)  # a Monday


def ratio_at(ts: datetime) -> float:
    """Deterministic fixture: depends on time of day only (weekly-repeating)."""

    return round(0.5 + 0.3 * ((ts.hour * 2 + ts.minute // 30) % 48) / 47, 4)


def add_segment_with_observations(start: datetime, end: datetime, seg_id: int = 1, skip=()):
    with session_scope() as s:
        s.add(TrafficSegment(id=seg_id, code=f"s{seg_id}", name=f"S{seg_id}", lat=12.9, lon=77.6))
        s.flush()
        t = start
        while t < end:
            if t not in skip:
                obs_time = t + timedelta(minutes=4)  # collector fetches a few minutes into the bucket
                s.add(TrafficObservation(segment_id=seg_id, observed_at=obs_time, source="fixture",
                                         current_speed_kmph=30 * ratio_at(t), free_flow_speed_kmph=30,
                                         speed_ratio=ratio_at(t)))
            t += timedelta(minutes=30)


def test_bucket_floors_to_half_hours():
    assert bucket(datetime(2026, 1, 5, 9, 44, 59, tzinfo=timezone.utc)) == datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)


def test_baselines_use_only_history_at_or_before_origin():
    origin = T0 + timedelta(days=14)
    target = origin + timedelta(minutes=60)
    history = {
        origin: 0.6,
        target - timedelta(days=7): 0.7,
        target - timedelta(days=14): 0.9,
        target: 0.1,  # the future: must never be used
    }
    p = baseline_predictions(history, origin, target)
    assert p == {"persistence": 0.6, "seasonal_naive": 0.7, "historical_average": pytest.approx(0.8)}
    assert baseline_predictions({origin: 0.6}, origin, target) == {
        "persistence": 0.6, "seasonal_naive": None, "historical_average": None,
    }


def test_logging_ignores_observations_after_now():
    add_segment_with_observations(T0, T0 + timedelta(days=1))
    now = T0 + timedelta(hours=10, minutes=10)
    with session_scope() as s:
        # A "future" observation inside the origin bucket but after `now`.
        s.add(TrafficObservation(segment_id=1, observed_at=now + timedelta(minutes=10), source="fixture",
                                 current_speed_kmph=3, free_flow_speed_kmph=30, speed_ratio=0.1))
    with session_scope() as s:
        stats = log_forecasts(s, now)
        assert stats["segments_forecast"] == 1
        preds = s.query(PredictionRecord).all()
    persistence = [p for p in preds if p.horizon_minutes == 30 and p.predicted_value is not None]
    assert persistence and all(p.predicted_value == pytest.approx(ratio_at(bucket(now))) for p in persistence[:1])
    # With < 1 week of history only persistence can be logged (3 horizons).
    assert len(preds) == 3 and stats["skipped_no_history"] == 6


def test_logging_is_idempotent_and_requires_fresh_observation():
    add_segment_with_observations(T0, T0 + timedelta(hours=6))
    with session_scope() as s:
        assert log_forecasts(s, T0 + timedelta(hours=5, minutes=5))["logged"] == 3
        assert log_forecasts(s, T0 + timedelta(hours=5, minutes=20))["already_logged"] == 3
        stale = log_forecasts(s, T0 + timedelta(hours=9))  # no observation in that bucket
        assert stale["segments_without_fresh_obs"] == 1 and stale["logged"] == 0


def test_cycle_resolves_actuals_and_reports_prediction_vs_actual():
    missing_bucket = T0 + timedelta(days=8, hours=6)
    add_segment_with_observations(T0, T0 + timedelta(days=9), skip={missing_bucket})
    now = T0 + timedelta(days=8)
    while now < T0 + timedelta(days=9) - timedelta(hours=3):
        run_cycle(now + timedelta(minutes=5))
        now += timedelta(minutes=30)
    final = T0 + timedelta(days=9)
    with session_scope() as s:
        resolve_actuals(s, final)
        rep = report(s, final)

    # Fixture repeats weekly, so seasonal naive and historical average are exact.
    for h in ("30m", "60m", "120m"):
        assert rep["candidates"]["seasonal_naive"][h]["mae"] == 0
        assert rep["candidates"]["historical_average"][h]["mae"] == 0
        assert rep["candidates"]["persistence"][h]["mae"] > 0
        assert set(rep["paired"][h]) == {"persistence", "seasonal_naive", "historical_average"}
    # Persistence error equals a hand computation over its own resolved forecasts.
    with session_scope() as s:
        from db.models import ModelVersion

        mv = s.query(ModelVersion).filter_by(name="baseline-persistence").one()
        recs = s.query(PredictionRecord).filter(
            PredictionRecord.model_version_id == mv.id, PredictionRecord.horizon_minutes == 30,
            PredictionRecord.actual_value.is_not(None),
        ).all()
        manual = sum(abs(r.predicted_value - r.actual_value) for r in recs) / len(recs)
    assert rep["candidates"]["persistence"]["30m"]["n"] == len(recs)
    assert rep["candidates"]["persistence"]["30m"]["mae"] == pytest.approx(manual, abs=1e-5)
    # The bucket without observations is counted as missing, never filled in.
    missing = sum(c[h]["missing_actual"] for c in rep["candidates"].values() for h in c)
    assert missing >= 3


def test_report_is_empty_and_read_only_without_logging():
    with session_scope() as s:
        rep = report(s)
        from db.models import ModelVersion

        assert rep["forecasts_logged"] == 0 and s.query(ModelVersion).count() == 0


def test_forecast_logging_failure_never_breaks_collection(monkeypatch):
    from core.settings import get_settings
    from traffic import collector

    async def fake_flow(settings, tomtom=None):
        return {"stored": 26, "duplicate": 0, "invalid": 0, "skipped": 0}

    def boom(now=None):
        raise RuntimeError("logging broke")

    monkeypatch.setattr(collector, "collect_flow", fake_flow)
    monkeypatch.setattr(online, "run_cycle", boom)
    stats = asyncio.run(collector.collect_flow_and_log(get_settings()))
    assert stats["stored"] == 26


def test_admin_endpoint_requires_admin(client, user_headers, admin_headers):
    assert client.get("/v1/admin/forecast/online").status_code == 401
    assert client.get("/v1/admin/forecast/online", headers=user_headers).status_code == 403
    body = client.get("/v1/admin/forecast/online", headers=admin_headers).json()
    assert body["kind"].startswith("prospective") and body["forecasts_logged"] == 0
