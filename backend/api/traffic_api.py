"""Collected traffic, weather and incident data (read), plus user incident reports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import current_user, settings_dep
from core.errors import AppError, NotFound
from core.settings import Settings
from db.models import Incident, TrafficSegment, User
from db.session import get_db
from providers.openmeteo import ATTRIBUTION
from traffic.state_engine import active_incidents, latest_segment_state, latest_weather, segment_history
from weather.service import WeatherService

router = APIRouter(tags=["traffic"])

COVERAGE_NOTE = (
    "Observations come from a fixed set of monitored sample points on major corridors "
    "(TomTom Flow Segment API). They are not city-wide coverage."
)


@router.get("/v1/traffic/segments")
def segments(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    items = latest_segment_state(db, settings.observation_stale_minutes)
    return {
        "segments": items,
        "coverage_note": COVERAGE_NOTE,
        "stale_after_minutes": settings.observation_stale_minutes,
        "source": "TomTom Traffic Flow (collected by Bengaluru Pulse)",
    }


@router.get("/v1/traffic/segments/{segment_id}/history")
def history(segment_id: int, hours: int = Query(48, ge=1, le=24 * 30), db: Session = Depends(get_db)):
    if db.get(TrafficSegment, segment_id) is None:
        raise NotFound("Segment not found")
    return {"segment_id": segment_id, "hours": hours, "observations": segment_history(db, segment_id, hours)}


@router.get("/v1/weather/current")
async def weather_current(
    lat: float = Query(12.9716, ge=12.5, le=13.5),
    lon: float = Query(77.5946, ge=77.2, le=78.0),
    settings: Settings = Depends(settings_dep),
):
    value = await WeatherService(settings).current(lat, lon)
    if value is None:
        raise AppError("Weather data currently unavailable", code="weather_unavailable", status_code=503)
    return value


@router.get("/v1/weather/at")
async def weather_at(
    when: datetime,
    lat: float = Query(12.9716, ge=12.5, le=13.5),
    lon: float = Query(77.5946, ge=77.2, le=78.0),
    settings: Settings = Depends(settings_dep),
):
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    value = await WeatherService(settings).at(lat, lon, when)
    if value is None:
        raise AppError("No weather forecast available for that time", code="weather_unavailable", status_code=503)
    return value


@router.get("/v1/weather/areas")
def weather_areas(db: Session = Depends(get_db)):
    rows = latest_weather(db)
    return {
        "attribution": ATTRIBUTION,
        "areas": [
            {
                "area": r.area, "lat": r.lat, "lon": r.lon,
                "observed_at": (r.observed_at if r.observed_at.tzinfo else r.observed_at.replace(tzinfo=timezone.utc)).isoformat(),
                "temperature_c": r.temperature_c, "precipitation_mm": r.precipitation_mm,
                "weather_code": r.weather_code, "wind_speed_kmh": r.wind_speed_kmh,
            }
            for r in rows
        ],
    }


def incident_dict(i: Incident) -> dict:
    return {
        "id": i.id, "source": i.source, "category": i.category, "severity": i.severity,
        "description": i.description, "road_from": i.road_from, "road_to": i.road_to,
        "lat": i.lat, "lon": i.lon, "geometry": i.geometry, "delay_s": i.delay_s,
        "start_time": i.start_time.isoformat() if i.start_time else None,
        "end_time": i.end_time.isoformat() if i.end_time else None,
        "last_seen_at": i.last_seen_at.isoformat() if i.last_seen_at else None,
        "status": i.status,
    }


@router.get("/v1/incidents")
def incidents(
    min_lat: Optional[float] = None, min_lon: Optional[float] = None,
    max_lat: Optional[float] = None, max_lon: Optional[float] = None,
    limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    rows = active_incidents(db, limit=5000)
    if None not in (min_lat, min_lon, max_lat, max_lon):
        rows = [r for r in rows if min_lat <= r.lat <= max_lat and min_lon <= r.lon <= max_lon]
    last = db.scalar(select(func.max(Incident.last_seen_at)).where(Incident.source == "tomtom"))
    return {
        "count": len(rows[:limit]),
        "total_active": len(rows),
        "last_sweep_at": last.isoformat() if last else None,
        "source": "TomTom Traffic Incidents (collected) + verified community reports",
        "incidents": [incident_dict(r) for r in rows[:limit]],
    }


class IncidentReport(BaseModel):
    category: str = Field(..., pattern="^(accident|road_closed|road_works|flooding|jam|broken_down_vehicle|dangerous_conditions|other)$")
    description: str = Field(..., min_length=5, max_length=500)
    lat: float = Field(..., ge=12.5, le=13.5)
    lon: float = Field(..., ge=77.2, le=78.0)


@router.post("/v1/incidents/report", status_code=201)
def report_incident(body: IncidentReport, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Community incident report. Held as `pending` until an admin publishes it."""

    recent = db.scalar(
        select(func.count(Incident.id)).where(
            Incident.reported_by == user.id,
            Incident.first_seen_at >= datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    if recent and recent >= 10:
        raise AppError("Report limit reached (10 per hour)", code="rate_limited", status_code=429)
    incident = Incident(
        source="community",
        external_id=f"u{user.id}-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        category=body.category, description=body.description, lat=body.lat, lon=body.lon,
        reported_by=user.id, status="pending", active=True,
    )
    db.add(incident)
    db.commit()
    return {"id": incident.id, "status": incident.status, "message": "Report received; it will be shown after moderation."}


@router.get("/v1/incidents/mine")
def my_reports(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Incident).where(Incident.reported_by == user.id).order_by(Incident.id.desc())).all()
    return {"reports": [incident_dict(r) for r in rows]}
