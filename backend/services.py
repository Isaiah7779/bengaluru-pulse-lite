"""Traffic intelligence services used by the FastAPI routes."""

import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import joblib
import pandas as pd
import requests

from config import Settings
from database import database
from domain import (
    LOCATION_META,
    compute_congestion,
    get_recommendation,
    get_signal,
    get_traffic_status,
    normalize_weather,
)
from schemas import CommuteInput, ForecastInput, TrafficIncident, TrafficInput

logger = logging.getLogger(__name__)


class ModelBundle:
    """Loads and owns ML artifacts for prediction."""

    def __init__(self, settings: Settings) -> None:
        self.model = self._load_artifact(settings.model_path)
        self.area_encoder = self._load_artifact(settings.area_encoder_path)
        self.road_encoder = self._load_artifact(settings.road_encoder_path)
        self.weather_encoder = self._load_artifact(settings.weather_encoder_path)

    @staticmethod
    def _load_artifact(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"Required model artifact not found: {path}")
        logger.info("Loading ML artifact: %s", path)
        return joblib.load(path)

    def predict(self, data: TrafficInput) -> Dict[str, Any]:
        meta = LOCATION_META[data.location]
        model_weather = normalize_weather(data.weather)

        input_data = pd.DataFrame(
            [
                {
                    "Area Name": self.area_encoder.transform([meta["area"]])[0],
                    "Road/Intersection Name": self.road_encoder.transform([meta["road"]])[0],
                    "Traffic Volume": data.traffic_volume,
                    "Average Speed": data.average_speed,
                    "Weather Conditions": self.weather_encoder.transform([model_weather])[0],
                }
            ]
        )

        prediction = self.model.predict(input_data)
        predicted_value = round(float(prediction[0]), 2)

        if data.traffic_volume < 20 and data.average_speed > 60:
            predicted_value = 5.0
        elif data.traffic_volume > 250 and data.average_speed < 20:
            predicted_value += 5

        predicted_value = round(max(0, min(predicted_value, 30)), 2)
        current_speed = max(data.average_speed, 5)
        delay_minutes = round(((50 / current_speed) - 1) * 15, 1)
        traffic_status = get_traffic_status(predicted_value)

        # Save successful ML predictions for dashboard history and analytics.
        try:
            database.save_prediction(
                location=data.location,
                traffic_volume=data.traffic_volume,
                average_speed=data.average_speed,
                weather=data.weather,
                predicted_congestion=predicted_value,
                traffic_status=traffic_status,
            )
        except Exception:
            # A database failure must not prevent a valid ML prediction
            # from being returned to the API client.
            logger.exception("Failed to save prediction to SQLite")

        return {
            "predicted_congestion": predicted_value,
            "traffic_status": traffic_status,
            "signal": get_signal(predicted_value),
            "recommendation": get_recommendation(predicted_value, data.location),
            "density_percent": round(min(predicted_value * 4, 100), 1),
            "estimated_delay_minutes": max(0, delay_minutes),
            "model_weather": model_weather,
            "location_meta": {
                "lat": meta["lat"],
                "lon": meta["lon"],
                "description": meta["description"],
            },
        }


class TrafficService:
    """Business logic for non-ML traffic intelligence endpoints."""

    def prediction_history(self) -> Dict[str, Any]:
        """Return prediction history stored in SQLite."""

        records = database.get_history()

        return {
            "count": len(records),
            "predictions": records,
        }

    def database_analytics(self) -> Dict[str, Any]:
        """Return analytics calculated from stored predictions."""

        return database.analytics()

    def forecast(self, data: ForecastInput) -> Dict[str, Any]:
        now = datetime.now()
        forecast_points = []

        for hours_ahead in range(13):
            future_time = now + timedelta(hours=hours_ahead)
            congestion = compute_congestion(
                data.location,
                future_time.hour,
                data.weather,
                random.uniform(-1.5, 1.5),
            )
            forecast_points.append(
                {
                    "label": future_time.strftime("%I:%M %p") if hours_ahead else "Now",
                    "hour": future_time.hour,
                    "congestion": congestion,
                    "status": get_traffic_status(congestion),
                    "hours_ahead": hours_ahead,
                }
            )

        peak = max(forecast_points, key=lambda item: item["congestion"])
        trough = min(forecast_points, key=lambda item: item["congestion"])
        return {
            "location": data.location,
            "forecast": forecast_points,
            "peak_congestion": peak,
            "best_travel_window": trough,
            "summary": (
                f"Peak congestion expected at {peak['label']} ({peak['status']}). "
                f"Best travel window: {trough['label']}."
            ),
        }

    def hotspots(self, weather: str = "Sunny") -> Dict[str, Any]:
        now = datetime.now()
        results = []

        for location, meta in LOCATION_META.items():
            congestion = compute_congestion(location, now.hour, weather, random.uniform(-1, 1))
            results.append(
                {
                    "location": location,
                    "congestion": congestion,
                    "status": get_traffic_status(congestion),
                    "signal": get_signal(congestion),
                    "lat": meta["lat"],
                    "lon": meta["lon"],
                    "description": meta["description"],
                    "is_peak_hour": now.hour in meta["peak_hours"],
                }
            )

        results.sort(key=lambda item: item["congestion"], reverse=True)
        return {
            "timestamp": now.isoformat(),
            "weather": weather,
            "hotspots": results,
            "worst_location": results[0]["location"],
            "best_location": results[-1]["location"],
            "city_average_congestion": round(
                sum(item["congestion"] for item in results) / len(results), 2
            ),
        }

    def analytics(self, location: str = "Silk Board", weather: str = "Sunny") -> Dict[str, Any]:
        meta = LOCATION_META[location]
        hourly_profile = []

        for hour in range(24):
            congestion = compute_congestion(location, hour, weather)
            hourly_profile.append(
                {
                    "hour": hour,
                    "label": datetime.now().replace(hour=hour, minute=0).strftime("%I %p"),
                    "congestion": congestion,
                    "status": get_traffic_status(congestion),
                }
            )

        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        weekly = [
            {
                "day": day,
                "avg_congestion": round(
                    meta["base_congestion"] * (0.6 if index >= 5 else 1.0)
                    + random.uniform(-1, 1),
                    2,
                ),
            }
            for index, day in enumerate(days)
        ]

        distribution = {
            status: sum(1 for hour in hourly_profile if hour["status"] == status)
            for status in ["LOW", "MODERATE", "HIGH", "SEVERE"]
        }

        return {
            "location": location,
            "hourly_profile": hourly_profile,
            "weekly_pattern": weekly,
            "congestion_distribution": distribution,
            "top_peak_hours": sorted(
                hourly_profile, key=lambda item: item["congestion"], reverse=True
            )[:3],
            "daily_avg_congestion": round(
                sum(hour["congestion"] for hour in hourly_profile) / 24, 2
            ),
            "risk_score": round(
                (
                    distribution["SEVERE"] * 4
                    + distribution["HIGH"] * 3
                    + distribution["MODERATE"] * 2
                    + distribution["LOW"]
                )
                / 24,
                1,
            ),
        }

    def commute_advisor(self, data: CommuteInput) -> Dict[str, Any]:
        arrival_hour = int(data.preferred_arrival.split(":")[0])
        suggestions = []

        for minutes_before in [75, 60, 45, 30]:
            departure_minutes = arrival_hour * 60 - minutes_before
            departure_hour = (departure_minutes // 60) % 24
            departure_minute = departure_minutes % 60
            origin_congestion = compute_congestion(data.origin, departure_hour, "Clear")
            destination_congestion = compute_congestion(data.destination, arrival_hour, "Clear")
            average_congestion = (origin_congestion + destination_congestion) / 2
            suggestions.append(
                {
                    "departure_time": f"{departure_hour:02d}:{departure_minute:02d}",
                    "origin_congestion": origin_congestion,
                    "destination_congestion": destination_congestion,
                    "avg_route_congestion": round(average_congestion, 2),
                    "status": get_traffic_status(average_congestion),
                    "estimated_travel_minutes": minutes_before,
                    "recommended": average_congestion < 12,
                }
            )

        best = min(suggestions, key=lambda item: item["avg_route_congestion"])
        return {
            "origin": data.origin,
            "destination": data.destination,
            "preferred_arrival": data.preferred_arrival,
            "departure_suggestions": suggestions,
            "recommended_departure": best["departure_time"],
            "route_alternatives": [
                {
                    "route": "Outer Ring Road (ORR)",
                    "type": "Expressway",
                    "typical_delay": "15-20 min",
                    "recommended_for": "Morning peak",
                },
                {
                    "route": "NICE Road Peripheral",
                    "type": "Toll Road",
                    "typical_delay": "5-10 min",
                    "recommended_for": "Evening peak, low toll",
                },
                {
                    "route": "Namma Metro Line",
                    "type": "Public Transit",
                    "typical_delay": "0-5 min",
                    "recommended_for": "Severe congestion days",
                },
            ],
            "advisory": (
                f"Best departure from {data.origin} is at {best['departure_time']} "
                f"for {data.preferred_arrival} arrival. Expected route congestion: "
                f"{best['status']}."
            ),
        }

    def historical_trends(self, weather: str = "Sunny") -> Dict[str, Any]:
        now = datetime.now()
        days_data: List[Dict[str, Any]] = []

        for days_ago in range(6, -1, -1):
            day = now - timedelta(days=days_ago)
            location_readings = {}
            for location, meta in LOCATION_META.items():
                factor = 0.65 if day.weekday() >= 5 else 1.0
                location_readings[location] = round(
                    meta["base_congestion"] * factor + random.uniform(-1.5, 1.5),
                    2,
                )
            days_data.append(
                {
                    "date": day.strftime("%a %d"),
                    "date_iso": day.strftime("%Y-%m-%d"),
                    **location_readings,
                }
            )

        city_trend = [
            {
                "date": day["date"],
                "avg": round(sum(day[location] for location in LOCATION_META) / len(LOCATION_META), 2),
            }
            for day in days_data
        ]

        return {
            "period": "Last 7 Days",
            "weather": weather,
            "locations": list(LOCATION_META.keys()),
            "trend_data": days_data,
            "city_trend": city_trend,
            "most_congested_today": max(LOCATION_META, key=lambda loc: days_data[-1][loc]),
            "least_congested_today": min(LOCATION_META, key=lambda loc: days_data[-1][loc]),
        }


class IncidentService:
    """Fetch and normalize live traffic incidents from an ASTraM-compatible feed."""

    def __init__(self, settings: Settings) -> None:
        self.url = settings.astram_url
        self.timeout_seconds = settings.astram_timeout_seconds

    def fetch_incidents(self) -> Dict[str, Any]:
        """Fetch live Bengaluru incidents from the configured endpoint."""

        try:
            response = requests.get(self.url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("ASTraM incident feed request failed: %s", exc)
            return self._fallback_incidents("connection_error")

        try:
            payload = response.json()
        except ValueError:
            logger.warning("ASTraM incident feed did not return JSON: %s", self.url)
            return self._fallback_incidents("invalid_json")

        raw_incidents = payload.get("incidents", [])
        if not isinstance(raw_incidents, list):
            return self._fallback_incidents("invalid_payload")

        incidents = [
            incident.dict()
            for incident in (
                self._normalize_incident(raw_incident) for raw_incident in raw_incidents
            )
            if incident is not None
        ]

        if not incidents:
            return self._fallback_incidents("empty_payload")

        return {
            "source": "ASTraM",
            "source_url": self.url,
            "status": "ok",
            "count": len(incidents),
            "incidents": incidents,
        }

    def _normalize_incident(self, raw_incident: Any) -> TrafficIncident | None:
        if not isinstance(raw_incident, dict):
            return None

        location_name = raw_incident.get("location_name") or raw_incident.get("location")
        severity = raw_incident.get("severity") or "moderate"
        disruption_type = raw_incident.get("disruption_type") or raw_incident.get("type")

        if not location_name or not disruption_type:
            return None

        return TrafficIncident(
            location_name=str(location_name),
            severity=str(severity).upper(),
            disruption_type=str(disruption_type),
            description=raw_incident.get("description"),
        )

    def _fallback_incidents(self, reason: str) -> Dict[str, Any]:
        incidents = self._simulate_incidents()
        return {
            "source": "Simulated",
            "source_url": self.url,
            "status": "fallback",
            "reason": reason,
            "count": len(incidents),
            "incidents": incidents,
        }

    def _simulate_incidents(self) -> List[Dict[str, Any]]:
        incident_types = [
            ("Accident", "🚗", "#ff3333", "HIGH"),
            ("Road Work", "🚧", "#ff8800", "MEDIUM"),
            ("Vehicle Breakdown", "🔧", "#ffcc00", "LOW"),
            ("Flooding", "🌊", "#ff3333", "HIGH"),
        ]
        locations = list(LOCATION_META.keys())
        incident_count = random.randint(0, 3)
        incidents = []

        for i in range(incident_count):
            disruption_type, icon, color, severity = random.choice(incident_types)
            location_name = random.choice(locations)
            incidents.append(
                {
                    "location_name": location_name,
                    "severity": severity,
                    "disruption_type": disruption_type,
                    "description": f"{icon} {disruption_type} reported near {location_name}. Expect delays and use caution.",
                    "icon": icon,
                    "color": color,
                    "source": "Simulated",
                }
            )

        return incidents

    def _unavailable(self, reason: str) -> Dict[str, Any]:
        return {
            "source": "ASTraM",
            "source_url": self.url,
            "status": "unavailable",
            "reason": reason,
            "count": 0,
            "incidents": [],
        }


import os
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def get_live_traffic(latitude: float, longitude: float):
    api_key = os.getenv("TOMTOM_API_KEY")

    if not api_key:
        raise ValueError("TOMTOM_API_KEY is not configured")

    url = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"

    params = {
        "point": f"{latitude},{longitude}",
        "unit": "KMPH",
        "key": api_key
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    return response.json()