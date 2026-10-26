"""Open-Meteo weather provider (free, no key; CC BY 4.0 attribution required)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from core.http import async_client

from core.settings import Settings
from providers.tomtom import ProviderError

ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"

# WMO weather interpretation codes used by Open-Meteo.
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog",
    48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Rain", 65: "Heavy rain", 80: "Rain showers",
    81: "Heavy rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

# Weather sampling points across Bengaluru (zones), used by the collector.
WEATHER_AREAS = {
    "central": (12.9716, 77.5946),
    "east": (12.9698, 77.7500),
    "north": (13.0358, 77.5970),
    "south": (12.8456, 77.6603),
    "west": (12.9719, 77.5000),
    "airport": (13.1989, 77.7068),
}


@dataclass
class WeatherReading:
    observed_at: datetime
    temperature_c: Optional[float]
    precipitation_mm: Optional[float]
    rain_mm: Optional[float]
    weather_code: Optional[int]
    wind_speed_kmh: Optional[float]
    visibility_m: Optional[float]

    @property
    def description(self) -> str:
        return WMO_CODES.get(self.weather_code, "Unknown") if self.weather_code is not None else "Unknown"

    @property
    def is_wet(self) -> bool:
        return (self.precipitation_mm or 0) > 0.1 or (self.weather_code or 0) >= 51


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) else None


def _ts(value: str, utc_offset_seconds: int) -> datetime:
    from datetime import timedelta

    local = datetime.fromisoformat(value)
    return (local - timedelta(seconds=utc_offset_seconds)).replace(tzinfo=timezone.utc)


def parse_current(payload: Dict[str, Any]) -> WeatherReading:
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict) or "time" not in current:
        raise ProviderError("Open-Meteo response missing current conditions")
    offset = int(payload.get("utc_offset_seconds") or 0)
    temp = _num(current.get("temperature_2m"))
    if temp is not None and not -10 <= temp <= 55:
        raise ProviderError("Open-Meteo temperature out of plausible range for Bengaluru")
    code = current.get("weather_code")
    return WeatherReading(
        observed_at=_ts(current["time"], offset),
        temperature_c=temp,
        precipitation_mm=_num(current.get("precipitation")),
        rain_mm=_num(current.get("rain")),
        weather_code=int(code) if isinstance(code, (int, float)) else None,
        wind_speed_kmh=_num(current.get("wind_speed_10m")),
        visibility_m=_num(current.get("visibility")),
    )


def parse_hourly(payload: Dict[str, Any]) -> List[WeatherReading]:
    hourly = (payload or {}).get("hourly") or {}
    times = hourly.get("time") or []
    offset = int(payload.get("utc_offset_seconds") or 0)
    out = []
    for i, t in enumerate(times):
        def col(name: str):
            values = hourly.get(name) or []
            return values[i] if i < len(values) else None

        code = col("weather_code")
        out.append(
            WeatherReading(
                observed_at=_ts(t, offset),
                temperature_c=_num(col("temperature_2m")),
                precipitation_mm=_num(col("precipitation")),
                rain_mm=_num(col("rain")),
                weather_code=int(code) if isinstance(code, (int, float)) else None,
                wind_speed_kmh=_num(col("wind_speed_10m")),
                visibility_m=_num(col("visibility")),
            )
        )
    return out


class OpenMeteoProvider:
    name = "open-meteo"
    variables = "temperature_2m,precipitation,rain,weather_code,wind_speed_10m,visibility"

    def __init__(self, settings: Settings) -> None:
        self.url = settings.openmeteo_url
        self.timeout = 8.0

    async def fetch(self, lat: float, lon: float, forecast_hours: int = 0) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "current": self.variables,
            "timezone": "Asia/Kolkata",
        }
        if forecast_hours:
            params["hourly"] = self.variables
            params["forecast_hours"] = forecast_hours
        try:
            async with async_client(self.timeout) as client:
                response = await client.get(self.url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Open-Meteo network error ({type(exc).__name__})") from None
        if response.status_code >= 400:
            raise ProviderError(f"Open-Meteo returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise ProviderError("Open-Meteo returned invalid JSON") from None

    async def current(self, lat: float, lon: float) -> WeatherReading:
        return parse_current(await self.fetch(lat, lon))
