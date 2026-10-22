"""Normalise, validate, de-duplicate and persist provider observations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, List

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from db.models import Incident, TrafficObservation, TrafficSegment, WeatherObservation
from providers.openmeteo import WeatherReading
from providers.tomtom import FlowReading, IncidentReading
from traffic.segments import MONITORED_POINTS

logger = logging.getLogger(__name__)


def minute_bucket(ts: datetime) -> datetime:
    ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(second=0, microsecond=0)


def ensure_segments(session: Session) -> List[TrafficSegment]:
    """Create monitored segments that do not exist yet (idempotent)."""

    existing = {s.code: s for s in session.scalars(select(TrafficSegment)).all()}
    for code, (name, lat, lon) in MONITORED_POINTS.items():
        if code not in existing:
            segment = TrafficSegment(code=code, name=name, lat=lat, lon=lon)
            session.add(segment)
            existing[code] = segment
    session.flush()
    return [s for s in existing.values() if s.active]


def store_flow(session: Session, segment: TrafficSegment, reading: FlowReading, source: str = "tomtom") -> bool:
    """Persist one flow reading. Returns False if it was a duplicate."""

    observed_at = minute_bucket(reading.fetched_at)
    duplicate = session.scalar(
        select(TrafficObservation.id).where(
            TrafficObservation.segment_id == segment.id,
            TrafficObservation.observed_at == observed_at,
            TrafficObservation.source == source,
        )
    )
    if duplicate:
        return False
    session.add(
        TrafficObservation(
            segment_id=segment.id,
            observed_at=observed_at,
            source=source,
            current_speed_kmph=reading.current_speed_kmph,
            free_flow_speed_kmph=reading.free_flow_speed_kmph,
            current_travel_time_s=reading.current_travel_time_s,
            free_flow_travel_time_s=reading.free_flow_travel_time_s,
            speed_ratio=round(min(reading.speed_ratio, 1.5), 4),
            confidence=reading.confidence,
            road_closure=reading.road_closure,
        )
    )
    session.flush()  # make the row visible to later duplicate checks in this session
    if reading.road_class:
        segment.road_class = reading.road_class
    if reading.geometry:
        segment.geometry = {"type": "LineString", "coordinates": reading.geometry}
    return True


def store_weather(session: Session, area: str, lat: float, lon: float, reading: WeatherReading, source: str = "open-meteo") -> bool:
    observed_at = minute_bucket(reading.observed_at)
    duplicate = session.scalar(
        select(WeatherObservation.id).where(
            WeatherObservation.area == area,
            WeatherObservation.observed_at == observed_at,
            WeatherObservation.source == source,
        )
    )
    if duplicate:
        return False
    session.add(
        WeatherObservation(
            area=area,
            lat=lat,
            lon=lon,
            observed_at=observed_at,
            source=source,
            temperature_c=reading.temperature_c,
            precipitation_mm=reading.precipitation_mm,
            rain_mm=reading.rain_mm,
            weather_code=reading.weather_code,
            wind_speed_kmh=reading.wind_speed_kmh,
            visibility_m=reading.visibility_m,
        )
    )
    session.flush()
    return True


def store_incidents(session: Session, readings: Iterable[IncidentReading], source: str = "tomtom") -> dict:
    """Upsert a full incident sweep; incidents absent from the sweep become inactive."""

    now = datetime.now(timezone.utc)
    seen = set()
    created = updated = 0
    for r in readings:
        seen.add(r.external_id)
        incident = session.scalar(
            select(Incident).where(Incident.source == source, Incident.external_id == r.external_id)
        )
        if incident is None:
            incident = Incident(source=source, external_id=r.external_id, first_seen_at=now)
            session.add(incident)
            created += 1
        else:
            updated += 1
        incident.category = r.category
        incident.severity = r.severity
        incident.description = r.description
        incident.road_from = r.road_from
        incident.road_to = r.road_to
        incident.lat = r.lat
        incident.lon = r.lon
        incident.geometry = r.geometry
        incident.delay_s = r.delay_s
        incident.start_time = r.start_time
        incident.end_time = r.end_time
        incident.last_seen_at = now
        incident.active = True
    deactivated = 0
    stmt = update(Incident).where(Incident.source == source, Incident.active.is_(True))
    if seen:
        stmt = stmt.where(Incident.external_id.not_in(seen))
    deactivated = session.execute(stmt.values(active=False)).rowcount or 0
    return {"created": created, "updated": updated, "deactivated": deactivated}
