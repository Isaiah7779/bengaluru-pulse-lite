"""Weather lookup for a place and time.

Current conditions: the nearest collected observation if fresh, else a live
Open-Meteo call (cached). Future departures: Open-Meteo hourly forecast.
Weather is reported as context and advisories; it is NOT converted into
travel-time adjustments (no evaluated model supports that).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select

from core.settings import Settings
from db.models import WeatherObservation
from db.session import session_scope
from providers.openmeteo import ATTRIBUTION, WMO_CODES, OpenMeteoProvider, WeatherReading, parse_current, parse_hourly
from providers.tomtom import ProviderError
from routing.geometry import haversine_m

logger = logging.getLogger(__name__)

_CACHE: Dict[Tuple[float, float, str], Tuple[float, Any]] = {}
_TTL_S = 900


def _cached(key, loader_result=None):
    hit = _CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def reading_to_dict(reading: WeatherReading, source: str, kind: str, area: Optional[str] = None) -> Dict[str, Any]:
    return {
        "kind": kind,  # observed | forecast
        "source": source,
        "attribution": ATTRIBUTION,
        "area": area,
        "time": reading.observed_at.isoformat(),
        "temperature_c": reading.temperature_c,
        "precipitation_mm": reading.precipitation_mm,
        "weather_code": reading.weather_code,
        "description": reading.description,
        "wind_speed_kmh": reading.wind_speed_kmh,
        "visibility_m": reading.visibility_m,
        "wet": reading.is_wet,
    }


class WeatherService:
    def __init__(self, settings: Settings, provider: Optional[OpenMeteoProvider] = None) -> None:
        self.settings = settings
        self.provider = provider or OpenMeteoProvider(settings)

    def _stored_current(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.settings.observation_stale_minutes)
        with session_scope() as session:
            rows = session.scalars(
                select(WeatherObservation).where(WeatherObservation.observed_at >= cutoff)
            ).all()
            if not rows:
                return None
            nearest = min(rows, key=lambda r: haversine_m((lon, lat), (r.lon, r.lat)))
            if haversine_m((lon, lat), (nearest.lon, nearest.lat)) > 25_000:
                return None
            observed = nearest.observed_at if nearest.observed_at.tzinfo else nearest.observed_at.replace(tzinfo=timezone.utc)
            reading = WeatherReading(
                observed_at=observed,
                temperature_c=nearest.temperature_c,
                precipitation_mm=nearest.precipitation_mm,
                rain_mm=nearest.rain_mm,
                weather_code=nearest.weather_code,
                wind_speed_kmh=nearest.wind_speed_kmh,
                visibility_m=nearest.visibility_m,
            )
            return reading_to_dict(reading, "open-meteo (collected)", "observed", nearest.area)

    async def current(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        try:
            stored = self._stored_current(lat, lon)
        except Exception:
            logger.exception("Stored weather lookup failed")
            stored = None
        if stored:
            return stored
        key = (round(lat, 2), round(lon, 2), "current")
        cached = _cached(key)
        if cached:
            return cached
        try:
            reading = parse_current(await self.provider.fetch(lat, lon))
        except ProviderError as exc:
            logger.warning("Live weather unavailable: %s", exc)
            return None
        value = reading_to_dict(reading, "open-meteo (live)", "observed")
        _CACHE[key] = (time.monotonic() + _TTL_S, value)
        return value

    async def at(self, lat: float, lon: float, when: datetime) -> Optional[Dict[str, Any]]:
        """Forecast for the hour containing `when` (up to 7 days ahead)."""

        now = datetime.now(timezone.utc)
        if when <= now + timedelta(minutes=45):
            return await self.current(lat, lon)
        hours = min(int((when - now).total_seconds() // 3600) + 2, 168)
        key = (round(lat, 2), round(lon, 2), f"hourly{hours}")
        payload = _cached(key)
        if payload is None:
            try:
                payload = await self.provider.fetch(lat, lon, forecast_hours=hours)
            except ProviderError as exc:
                logger.warning("Weather forecast unavailable: %s", exc)
                return None
            _CACHE[key] = (time.monotonic() + _TTL_S, payload)
        readings = parse_hourly(payload)
        if not readings:
            return None
        best = min(readings, key=lambda r: abs((r.observed_at - when).total_seconds()))
        if abs((best.observed_at - when).total_seconds()) > 5400:
            return None
        return reading_to_dict(best, "open-meteo (forecast)", "forecast")


def advisories(weather: Optional[Dict[str, Any]], vehicle: str) -> list[str]:
    if not weather:
        return []
    notes = []
    if weather.get("wet") and vehicle in {"bicycle", "walk", "motorcycle"}:
        notes.append(
            f"{weather['description']} expected ({weather['kind']}, {weather['source']}): "
            f"exposed {vehicle} travel; allow extra time. Travel times are not weather-adjusted."
        )
    visibility = weather.get("visibility_m")
    if isinstance(visibility, (int, float)) and visibility < 1000:
        notes.append(f"Low visibility ({visibility:.0f} m) reported.")
    code = weather.get("weather_code")
    if code in (95, 96, 99):
        notes.append("Thunderstorm conditions: waterlogging is common on low-lying Bengaluru roads.")
    return notes


__all__ = ["WeatherService", "advisories", "WMO_CODES"]
