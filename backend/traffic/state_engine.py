"""Read-side view of collected traffic: latest state, freshness and history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import Incident, ProviderCall, TrafficObservation, TrafficSegment, WeatherObservation


def congestion_level(speed_ratio: float, road_closure: bool = False) -> str:
    """Project display category from current/free-flow speed ratio."""

    if road_closure:
        return "CLOSED"
    if speed_ratio >= 0.85:
        return "FREE"
    if speed_ratio >= 0.65:
        return "MODERATE"
    if speed_ratio >= 0.45:
        return "HEAVY"
    return "SEVERE"


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def latest_segment_state(session: Session, stale_minutes: int) -> List[Dict[str, Any]]:
    latest = (
        select(TrafficObservation.segment_id, func.max(TrafficObservation.observed_at).label("ts"))
        .group_by(TrafficObservation.segment_id)
        .subquery()
    )
    rows = session.execute(
        select(TrafficSegment, TrafficObservation)
        .join(latest, latest.c.segment_id == TrafficSegment.id, isouter=True)
        .join(
            TrafficObservation,
            (TrafficObservation.segment_id == TrafficSegment.id)
            & (TrafficObservation.observed_at == latest.c.ts),
            isouter=True,
        )
        .where(TrafficSegment.active.is_(True))
        .order_by(TrafficSegment.id)
    ).all()
    now = datetime.now(timezone.utc)
    out = []
    for segment, obs in rows:
        item: Dict[str, Any] = {
            "segment_id": segment.id,
            "code": segment.code,
            "name": segment.name,
            "lat": segment.lat,
            "lon": segment.lon,
            "road_class": segment.road_class,
            "geometry": segment.geometry,
            "observation": None,
            "status": "no_data",
        }
        if obs is not None:
            observed = _aware(obs.observed_at)
            age_min = (now - observed).total_seconds() / 60
            item["observation"] = {
                "observed_at": observed.isoformat(),
                "age_minutes": round(age_min, 1),
                "source": obs.source,
                "current_speed_kmph": obs.current_speed_kmph,
                "free_flow_speed_kmph": obs.free_flow_speed_kmph,
                "speed_ratio": obs.speed_ratio,
                "confidence": obs.confidence,
                "road_closure": obs.road_closure,
                "congestion": congestion_level(obs.speed_ratio, obs.road_closure),
            }
            item["status"] = "stale" if age_min > stale_minutes else "fresh"
        out.append(item)
    return out


def segment_history(session: Session, segment_id: int, hours: int = 48) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = session.scalars(
        select(TrafficObservation)
        .where(TrafficObservation.segment_id == segment_id, TrafficObservation.observed_at >= since)
        .order_by(TrafficObservation.observed_at)
    ).all()
    return [
        {
            "observed_at": _aware(r.observed_at).isoformat(),
            "current_speed_kmph": r.current_speed_kmph,
            "free_flow_speed_kmph": r.free_flow_speed_kmph,
            "speed_ratio": r.speed_ratio,
        }
        for r in rows
    ]


def latest_weather(session: Session) -> List[Dict[str, Any]]:
    latest = (
        select(WeatherObservation.area, func.max(WeatherObservation.observed_at).label("ts"))
        .group_by(WeatherObservation.area)
        .subquery()
    )
    rows = session.scalars(
        select(WeatherObservation).join(
            latest,
            (latest.c.area == WeatherObservation.area) & (latest.c.ts == WeatherObservation.observed_at),
        )
    ).all()
    return rows


def active_incidents(session: Session, limit: int = 200) -> List[Incident]:
    return session.scalars(
        select(Incident)
        .where(Incident.active.is_(True), Incident.status == "published")
        .order_by(Incident.severity.desc().nulls_last(), Incident.last_seen_at.desc())
        .limit(limit)
    ).all()


def freshness_report(session: Session, stale_minutes: int) -> Dict[str, Any]:
    """Data-freshness summary for the admin dashboard."""

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def last(model, column) -> Optional[str]:
        ts = session.scalar(select(func.max(column)))
        return _aware(ts).isoformat() if ts else None

    calls = session.execute(
        select(ProviderCall.provider, ProviderCall.purpose, ProviderCall.ok, func.count())
        .where(ProviderCall.called_at >= day_start)
        .group_by(ProviderCall.provider, ProviderCall.purpose, ProviderCall.ok)
    ).all()
    segments = latest_segment_state(session, stale_minutes)
    return {
        "generated_at": now.isoformat(),
        "traffic": {
            "segments_total": len(segments),
            "segments_fresh": sum(1 for s in segments if s["status"] == "fresh"),
            "segments_stale": sum(1 for s in segments if s["status"] == "stale"),
            "segments_no_data": sum(1 for s in segments if s["status"] == "no_data"),
            "observations_total": session.scalar(select(func.count(TrafficObservation.id))) or 0,
            "last_observation_at": last(TrafficObservation, TrafficObservation.observed_at),
            "first_observation_at": (
                _aware(session.scalar(select(func.min(TrafficObservation.observed_at)))).isoformat()
                if session.scalar(select(func.count(TrafficObservation.id)))
                else None
            ),
        },
        "weather": {
            "observations_total": session.scalar(select(func.count(WeatherObservation.id))) or 0,
            "last_observation_at": last(WeatherObservation, WeatherObservation.observed_at),
        },
        "incidents": {
            "active": session.scalar(select(func.count(Incident.id)).where(Incident.active.is_(True))) or 0,
            "last_seen_at": last(Incident, Incident.last_seen_at),
        },
        "provider_calls_today": [
            {"provider": p, "purpose": purpose, "ok": ok, "count": n} for p, purpose, ok, n in calls
        ],
        "stale_after_minutes": stale_minutes,
    }
