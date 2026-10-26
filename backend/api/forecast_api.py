"""Forecast model registry and segment forecasts (only from evaluated, active models)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import AppError, NotFound
from db.models import EvaluationRecord, ModelVersion, TrafficSegment
from db.session import get_db
from forecasting.predictor import SEGMENT_TASK, forecast_lookup

router = APIRouter(prefix="/v1/forecast", tags=["forecast"])


@router.get("/models")
def models(db: Session = Depends(get_db)):
    """All registered model versions with their recorded (measured) evaluation metrics."""

    out = []
    for m in db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all():
        evals = db.scalars(select(EvaluationRecord).where(EvaluationRecord.model_version_id == m.id)).all()
        out.append({
            "name": m.name, "version": m.version, "task": m.task, "algorithm": m.algorithm, "status": m.status,
            "dataset": m.dataset,
            "dataset_start": m.dataset_start.isoformat() if m.dataset_start else None,
            "dataset_end": m.dataset_end.isoformat() if m.dataset_end else None,
            "splits": m.splits, "notes": m.notes,
            "metrics": [{"split": e.split, "horizon": e.horizon, "candidate": e.candidate, "metric": e.metric, "value": round(e.value, 4), "n": e.n_samples} for e in evals],
        })
    active = [m for m in out if m["status"] == "active" and m["task"] == SEGMENT_TASK]
    return {
        "models": out,
        "routing_forecasts_enabled": bool(active),
        "note": None if active else (
            "No segment-level model has passed chronological evaluation against baselines yet; "
            "routes use TomTom's provider prediction for future departures."
        ),
    }


@router.get("/segments/{segment_id}")
def segment_forecast(segment_id: int, at: Optional[datetime] = Query(None), db: Session = Depends(get_db)):
    if db.get(TrafficSegment, segment_id) is None:
        raise NotFound("Segment not found")
    lookup = forecast_lookup()
    if lookup is None:
        raise AppError(
            "No evaluated forecasting model is active; forecasts are not available yet.",
            code="forecast_unavailable", status_code=503,
        )
    target = at or datetime.now(timezone.utc)
    target = target if target.tzinfo else target.replace(tzinfo=timezone.utc)
    result = lookup(segment_id, target)
    if result is None:
        raise AppError("Insufficient recent observations to forecast this segment", code="forecast_unavailable", status_code=503)
    return result
