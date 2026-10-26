"""Retention, privacy and housekeeping jobs (run daily by the collector)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import delete

from core.settings import Settings
from db.models import ProviderCall, RevokedToken, TrafficObservation, Trip, WeatherObservation
from db.session import session_scope

logger = logging.getLogger("pulse.maintenance")


def run_retention(settings: Settings, now: datetime | None = None) -> Dict[str, int]:
    from community.service import mark_stale, purge_old_traces

    now = now or datetime.now(timezone.utc)
    obs_cutoff = now - timedelta(days=settings.retention_observation_days)
    trip_cutoff = now - timedelta(days=settings.retention_trip_days)
    with session_scope() as s:
        result = {
            "traffic_observations": s.execute(delete(TrafficObservation).where(TrafficObservation.observed_at < obs_cutoff)).rowcount,
            "weather_observations": s.execute(delete(WeatherObservation).where(WeatherObservation.observed_at < obs_cutoff)).rowcount,
            "trips": s.execute(delete(Trip).where(Trip.created_at < trip_cutoff)).rowcount,
            "revoked_tokens": s.execute(delete(RevokedToken).where(RevokedToken.expires_at < now)).rowcount,
            "provider_calls": s.execute(delete(ProviderCall).where(ProviderCall.called_at < now - timedelta(days=90))).rowcount,
            "gps_traces_purged": purge_old_traces(s, settings, now),
            "shortcuts_marked_stale": mark_stale(s, now),
        }
    logger.info("Retention: %s", result)
    return result


def run_retrain() -> Dict:
    """Attempt the operational forecasting pipeline; it refuses until data suffices."""

    from core.settings import BASE_DIR
    from forecasting.pipeline import SEGMENTS, load_segments, run

    df, report = load_segments()
    result = run(SEGMENTS, df, report, BASE_DIR / "evaluation" / "v2")
    summary = {"status": result.get("status"), "span_days": result.get("span_days"),
               "activated": (result.get("activation") or {}).get("activated")}
    logger.info("Retrain: %s", summary)
    return summary
