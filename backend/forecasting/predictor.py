"""Inference hook used by routing and the forecast API.

A forecast is served only from a model version whose status is `active` in the
registry. Activation is gated by `forecasting.evaluate` (the model must beat the
persistence and historical-average baselines on chronologically held-out data).
Without an active model this module returns None and the product says so.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select

from db.models import ModelVersion
from db.session import session_scope

logger = logging.getLogger(__name__)

SEGMENT_TASK = "segment_speed_ratio"

_loaded: Dict[str, Any] = {}


def active_model(task: str = SEGMENT_TASK) -> Optional[ModelVersion]:
    try:
        with session_scope() as session:
            return session.scalar(
                select(ModelVersion)
                .where(ModelVersion.task == task, ModelVersion.status == "active")
                .order_by(ModelVersion.created_at.desc())
                .limit(1)
            )
    except Exception:
        logger.exception("Model registry lookup failed")
        return None


def forecast_lookup() -> Optional[Callable[[int, datetime], Optional[Dict[str, Any]]]]:
    """Return a (segment_id, target_time) -> forecast callable, or None."""

    model = active_model()
    if model is None:
        return None
    from forecasting.segment_model import SegmentForecaster

    forecaster = SegmentForecaster.load(model)
    if forecaster is None:
        return None
    return forecaster.predict_for
