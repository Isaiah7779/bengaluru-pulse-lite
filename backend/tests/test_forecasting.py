"""Forecasting pipeline mechanics.

The series below are SYNTHETIC TEST FIXTURES generated in-test to exercise the
pipeline (splits, baselines, registry, activation, serving). They are never
stored outside the temporary test database and never reported as results.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from db.models import EvaluationRecord, ModelVersion, TrafficObservation, TrafficSegment
from db.session import session_scope
from forecasting import pipeline
from forecasting.pipeline import SEGMENTS, _fit_predict, candidates, chronological_split, load_research, metrics, supervised, to_grid


def synthetic_segments(days=21, segments=3, seed=0, signal=True) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    times = pd.date_range(start, periods=days * 48, freq="30min", tz="UTC")
    rows = []
    for sid in range(1, segments + 1):
        level = 0.7
        for t in times:
            hour = (t.hour + 5.5) % 24
            daily = -0.25 * np.exp(-((hour - 9) ** 2) / 2) - 0.3 * np.exp(-((hour - 18.5) ** 2) / 3)
            level = 0.8 * level + 0.2 * (0.85 + daily) + (rng.normal(0, 0.02) if signal else 0)
            value = level if signal else rng.uniform(0.3, 1.0)
            rows.append((sid, t, float(np.clip(value, 0.05, 1.2))))
    return pd.DataFrame(rows, columns=["series", "time", "speed_ratio"])


def test_metrics_basic():
    m = metrics(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 5.0]))
    assert m["mae"] == pytest.approx(2 / 3) and m["rmse"] == pytest.approx((4 / 3) ** 0.5) and m["n"] == 3


def test_research_loader_accepts_compatible_schema_and_converts_values(tmp_path):
    source = tmp_path / "compatible.csv"
    pd.DataFrame({
        "Timestamp": ["2024-01-01", "2024-01-02"],
        "Series": [" road A ", "road A"],
        "Target": ["12.5", "80"],
    }).to_csv(source, index=False)
    frame, report = load_research(source)
    assert list(frame.columns) == ["series", "time", "congestion"]
    assert frame["series"].tolist() == ["road A", "road A"]
    assert frame["congestion"].tolist() == [12.5, 80.0]
    assert str(frame["time"].dtype).endswith(", UTC]")
    assert report["invalid_numeric_by_field"]["congestion"] == 0


def test_research_loader_reports_and_drops_invalid_values(tmp_path):
    source = tmp_path / "invalid.csv"
    pd.DataFrame({
        "Date": ["2024-01-01", "not-a-date", "2024-01-03", "2024-01-04"],
        "Area Name": [" A ", "A", "A", None],
        "Road/Intersection Name": ["R", "R", "R", "R"],
        "Congestion Level": ["25.5", "30", "not-numeric", "45"],
    }).to_csv(source, index=False)
    frame, report = load_research(source)
    assert len(frame) == 1 and frame.iloc[0]["congestion"] == 25.5
    assert report["invalid_timestamps_dropped"] == 1
    assert report["missing_series_dropped"] == 1
    assert report["invalid_numeric_by_field"]["congestion"] == 1
    assert report["missing_or_invalid_target_dropped"] == 1
    assert report["missing_values_by_field"]["congestion"] == 0


def test_research_loader_rejects_missing_required_fields(tmp_path):
    source = tmp_path / "missing.csv"
    pd.DataFrame({"Date": ["2024-01-01"], "Congestion Level": [25]}).to_csv(source, index=False)
    with pytest.raises(ValueError, match="Missing required fields.*series"):
        load_research(source)


def test_imputation_and_zscore_fit_only_on_chronological_training_rows():
    candidate = next(c for c in candidates() if c.name == "ridge")
    model = candidate.factory()
    train = pd.DataFrame({"feature": [1.0, 3.0, np.nan], "other": [10.0, 20.0, 30.0]})
    evaluate = pd.DataFrame({"feature": [1000.0], "other": [1000.0]})
    _fit_predict(model, train, np.array([1.0, 2.0, 3.0]), evaluate)
    imputer = model.named_steps["simpleimputer"]
    scaler = model.named_steps["standardscaler"]
    assert imputer.statistics_.tolist() == pytest.approx([2.0, 20.0])
    assert scaler.mean_.tolist() == pytest.approx([2.0, 20.0])
    assert scaler.scale_.tolist() == pytest.approx([np.sqrt(2 / 3), np.sqrt(200 / 3)])


def test_split_is_chronological_and_features_have_no_future_leakage():
    grid = to_grid(synthetic_segments(days=15), SEGMENTS)
    data = supervised(grid, SEGMENTS, horizon=2)
    train, val, test, splits = chronological_split(data, SEGMENTS)
    assert train["target_time"].max() < val["target_time"].min() <= val["target_time"].max() < test["target_time"].min()
    # last_value at an origin equals the observation at that origin (never the target).
    row = data.iloc[500]
    observed = grid[(grid.series == row.series) & (grid.time == row.origin)]["speed_ratio"].iloc[0]
    assert row["last_value"] == pytest.approx(observed)
    assert row["target_time"] - row["origin"] == pd.Timedelta(minutes=60)


def test_insufficient_data_is_reported(tmp_path):
    report = pipeline.run(SEGMENTS, synthetic_segments(days=3), {}, tmp_path, register=False)
    assert report["status"] == "insufficient_data" and "14" in report["reason"]


def test_pipeline_registers_and_activates_only_when_beating_baselines(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "candidates", _fast_candidates)
    report = pipeline.run(SEGMENTS, synthetic_segments(days=21), {}, tmp_path / "evaluation" / "v2")
    assert report["status"] == "evaluated"
    for h in ("30m", "60m", "120m"):
        r = report["horizons"][h]
        assert {"baseline:persistence", "baseline:seasonal_naive", "baseline:historical_average"} <= set(r["test"])
        assert r["splits"]["sizes"]["test"] > 0
    with session_scope() as s:
        mv = s.query(ModelVersion).one()
        assert mv.status == ("active" if report["activation"]["activated"] else "candidate")
        assert s.query(EvaluationRecord).filter_by(model_version_id=mv.id, split="test", metric="mae").count() >= 12


def test_noise_only_series_is_not_activated(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "candidates", _fast_candidates)
    report = pipeline.run(SEGMENTS, synthetic_segments(days=21, signal=False), {}, tmp_path / "evaluation" / "v2")
    assert report["activation"]["activated"] is False
    with session_scope() as s:
        assert s.query(ModelVersion).one().status == "candidate"


def _fast_candidates():
    return [c for c in candidates() if c.name == "ridge"]


def test_active_model_serves_forecasts_within_evaluated_horizons(tmp_path, monkeypatch):
    from core.settings import get_settings
    from forecasting.predictor import forecast_lookup

    monkeypatch.setattr(pipeline, "candidates", _fast_candidates)
    # Test-only: force activation so the serving path is exercised regardless of fixture skill.
    monkeypatch.setattr(pipeline, "ACTIVATION_MIN_IMPROVEMENT", -10.0)
    df = synthetic_segments(days=21, segments=3)
    report = pipeline.run(SEGMENTS, df, {}, tmp_path / "evaluation" / "v2")
    assert report["activation"]["activated"]
    settings = get_settings()
    monkeypatch.setattr(settings, "model_registry_dir", str(tmp_path / "models"))
    now = df["time"].max().to_pydatetime() + timedelta(minutes=10)
    with session_scope() as s:
        for sid in (1, 2, 3):
            s.add(TrafficSegment(id=sid, code=f"s{sid}", name=f"S{sid}", lat=12.9, lon=77.6))
        s.flush()
        for r in df.itertuples():
            s.add(TrafficObservation(segment_id=r.series, observed_at=r.time.to_pydatetime(), source="fixture",
                                     current_speed_kmph=30 * r.speed_ratio, free_flow_speed_kmph=30, speed_ratio=r.speed_ratio))
    lookup = forecast_lookup()
    assert lookup is not None
    from forecasting.segment_model import SegmentForecaster

    forecaster = lookup.__self__
    assert isinstance(forecaster, SegmentForecaster)
    one_hour = forecaster.predict_for(1, now + timedelta(minutes=50), now=now)
    assert one_hour and one_hour["horizon"] == "60m" and 0 <= one_hour["predicted_speed_ratio"] <= 1.5
    assert forecaster.predict_for(1, now + timedelta(hours=6), now=now) is None  # beyond evaluated horizons
