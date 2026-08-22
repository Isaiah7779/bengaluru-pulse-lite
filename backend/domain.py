"""Domain constants and traffic helper functions."""

import math
from datetime import datetime
from typing import Dict, List, TypedDict


class LocationMeta(TypedDict):
    area: str
    road: str
    lat: float
    lon: float
    peak_hours: List[int]
    base_congestion: int
    description: str


LOCATION_META: Dict[str, LocationMeta] = {
    "Marathahalli Bridge": {
        "area": "Whitefield",
        "road": "Marathahalli Bridge",
        "lat": 12.9591,
        "lon": 77.6974,
        "peak_hours": [8, 9, 18, 19, 20],
        "base_congestion": 14,
        "description": "Major IT corridor bridge connecting Outer Ring Road",
    },
    "Silk Board": {
        "area": "Koramangala",
        "road": "Silk Board Junction",
        "lat": 12.9177,
        "lon": 77.6238,
        "peak_hours": [8, 9, 17, 18, 19],
        "base_congestion": 20,
        "description": "Notorious bottleneck at the junction of three major roads",
    },
    "KR Puram": {
        "area": "Whitefield",
        "road": "ITPL Main Road",
        "lat": 13.0077,
        "lon": 77.6955,
        "peak_hours": [7, 8, 9, 18, 19],
        "base_congestion": 16,
        "description": "Key eastern gateway with heavy freight and commuter traffic",
    },
    "Hebbal": {
        "area": "Hebbal",
        "road": "Hebbal Flyover",
        "lat": 13.0358,
        "lon": 77.5970,
        "peak_hours": [8, 9, 17, 18],
        "base_congestion": 13,
        "description": "Northern flyover junction linking airport corridor",
    },
    "Whitefield": {
        "area": "Whitefield",
        "road": "ITPL Main Road",
        "lat": 12.9698,
        "lon": 77.7500,
        "peak_hours": [9, 10, 18, 19, 20],
        "base_congestion": 15,
        "description": "Prime IT hub with tech-park dense traffic patterns",
    },
    "Electronic City": {
        "area": "Electronic City",
        "road": "Hosur Road",
        "lat": 12.8456,
        "lon": 77.6603,
        "peak_hours": [8, 9, 18, 19],
        "base_congestion": 12,
        "description": "Southern tech corridor with elevated highway access",
    },
}

WEATHER_ALIASES = {
    "Sunny": "Clear",
    "Cloudy": "Overcast",
    "Rainy": "Rain",
    "Clear": "Clear",
    "Overcast": "Overcast",
    "Fog": "Fog",
    "Rain": "Rain",
    "Windy": "Windy",
}

WEATHER_IMPACT = {
    "Clear": 0,
    "Overcast": 2,
    "Fog": 4,
    "Rain": 5,
    "Windy": 3,
}

STATUS_THRESHOLDS = {
    "LOW": 8,
    "MODERATE": 15,
    "HIGH": 22,
}


def normalize_weather(weather: str) -> str:
    """Map user-facing weather labels to model-trained labels."""

    return WEATHER_ALIASES.get(weather.strip(), "Clear")


def get_traffic_status(value: float) -> str:
    """Convert congestion index to a severity label."""

    if value < STATUS_THRESHOLDS["LOW"]:
        return "LOW"
    if value < STATUS_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    if value < STATUS_THRESHOLDS["HIGH"]:
        return "HIGH"
    return "SEVERE"


def get_signal(value: float) -> str:
    """Convert congestion index to traffic signal color."""

    if value < STATUS_THRESHOLDS["LOW"]:
        return "GREEN"
    if value < STATUS_THRESHOLDS["MODERATE"]:
        return "YELLOW"
    return "RED"


def compute_congestion(location: str, hour: int, weather: str, noise: float = 0) -> float:
    """Estimate congestion using rush-hour, weather, and weekend effects."""

    meta = LOCATION_META[location]
    normalized_weather = normalize_weather(weather)
    morning_peak = 8 * math.exp(-0.5 * ((hour - 8.5) / 1.2) ** 2)
    evening_peak = 9 * math.exp(-0.5 * ((hour - 18.5) / 1.5) ** 2)
    weekend_factor = -4 if datetime.now().weekday() >= 5 else 0
    raw = (
        meta["base_congestion"]
        + morning_peak
        + evening_peak
        + WEATHER_IMPACT.get(normalized_weather, 0)
        + weekend_factor
        + noise
    )
    return round(max(0, min(raw, 30)), 2)


def get_recommendation(value: float, location: str) -> str:
    """Return a user-facing travel recommendation."""

    meta = LOCATION_META[location]
    if value < STATUS_THRESHOLDS["LOW"]:
        return (
            f"Traffic flow is smooth at {location}. Normal route recommended. "
            "Expected travel time is minimal."
        )
    if value < STATUS_THRESHOLDS["MODERATE"]:
        return (
            f"Moderate congestion at {location}. {meta['description']}. "
            "Consider alternate roads or delay by 15-20 minutes."
        )
    if value < STATUS_THRESHOLDS["HIGH"]:
        return (
            f"Heavy congestion at {location}. Delay of 25-40 minutes expected. "
            "Use Ring Road or NICE Road alternatives."
        )
    return (
        f"Severe gridlock at {location}. Immediate alternate route advised. "
        "Consider metro or WFH if possible."
    )
