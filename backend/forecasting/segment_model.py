"""Serve forecasts from an *active* segment model (see forecasting.pipeline).

Forecasts are produced only for horizons the model was evaluated on
(30/60/120 minutes, nearest within one step); anything further ahead returns
None rather than an unevaluated extrapolation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select

from core.settings import get_settings
from db.models import EvaluationRecord, ModelVersion, TrafficObservation
from db.session import session_scope
from forecasting.pipeline import SEGMENTS, model_matrix, supervised, to_grid

logger = logging.getLogger(__name__)
STEP = timedelta(minutes=30)
HISTORY = timedelta(days=8)  # enough for the one-week lag feature


class SegmentForecaster:
    def __init__(self, model: ModelVersion, artifact: Dict[str, Any], test_mae: Dict[str, float]) -> None:
        self.model_name = f"{model.name}@{model.version}"
        self.artifact = artifact
        self.test_mae = test_mae

    @classmethod
    def load(cls, model: ModelVersion) -> Optional["SegmentForecaster"]:
        path = get_settings().registry_path / (model.artifact_path or "")
        if not path.is_file():
            logger.warning("Active model artifact missing: %s", path.name)
            return None
        with session_scope() as s:
            rows = s.scalars(
                select(EvaluationRecord).where(
                    EvaluationRecord.model_version_id == model.id, EvaluationRecord.split == "test",
                    EvaluationRecord.metric == "mae", EvaluationRecord.candidate.like("model:%"),
                )
            ).all()
            test_mae = {r.horizon: round(r.value, 4) for r in rows}
        return cls(model, joblib.load(path), test_mae)

    def _history(self, segment_id: int, now: datetime) -> pd.DataFrame:
        with session_scope() as s:
            rows = s.execute(
                select(TrafficObservation.segment_id, TrafficObservation.observed_at, TrafficObservation.speed_ratio)
                .where(TrafficObservation.segment_id == segment_id, TrafficObservation.observed_at >= now - HISTORY)
            ).all()
        df = pd.DataFrame(rows, columns=["series", "time", "speed_ratio"])
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"], utc=True).dt.floor("30min")
            df = df.groupby(["series", "time"], as_index=False)["speed_ratio"].mean()
        return df

    def predict_for(self, segment_id: int, target_time: datetime, now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        origin = pd.Timestamp(now).floor("30min")
        steps = round((target_time - origin.to_pydatetime()) / STEP)
        available = {v: k for k, v in self.artifact["horizons"].items() if k in self.artifact["models"]}
        if steps < 1 or not available:
            return None
        nearest = min(available, key=lambda s: abs(s - steps))
        if abs(nearest - steps) > 1:
            return None  # beyond evaluated horizons: no claim
        horizon_label = available[nearest]
        hist = self._history(segment_id, now)
        if hist.empty or (origin - hist["time"].max()) > pd.Timedelta(hours=2):
            return None  # no recent observation to forecast from
        # Append a placeholder target row so the origin row survives supervised().
        grid = to_grid(hist, SEGMENTS)
        future = pd.DataFrame({"time": [origin + i * pd.Timedelta(minutes=30) for i in range(1, nearest + 1)],
                               "speed_ratio": [0.0] * nearest, "series": segment_id})
        grid = pd.concat([grid[grid["time"] <= origin], future], ignore_index=True)
        data = supervised(grid, SEGMENTS, nearest)
        row = data[data["origin"] == origin]
        if row.empty:
            return None
        bundle = self.artifact["models"][horizon_label]
        X = model_matrix(row, bundle["columns"], bundle["hist_table"], SEGMENTS)
        # Older saved artifacts carry their own training-derived fill values.
        if "fill" in bundle:
            X = X.fillna(bundle["fill"])
        value = float(np.clip(bundle["model"].predict(X)[0], *SEGMENTS.clip))
        return {
            "segment_id": segment_id,
            "target_time": (origin + nearest * pd.Timedelta(minutes=30)).isoformat(),
            "horizon": horizon_label,
            "predicted_speed_ratio": round(value, 3),
            "model": self.model_name,
            "test_mae": self.test_mae.get(horizon_label),
            "basis": "Bengaluru Pulse model (chronologically evaluated, beat baselines on test data)",
        }
