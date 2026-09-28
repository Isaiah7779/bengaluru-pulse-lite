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
        """
        Calculate a traffic-aware commute recommendation using the TomTom
        Routing API.

        V2 improvements:
        - Uses TomTom's real-time traffic-aware routing.
        - Requests up to two alternatives (three routes total when available).
        - Requests text guidance so the response contains real road/street names.
        - Preserves actual route identity instead of inventing generic names such
          as "Alternative Route 2".
        - Recommends the fastest returned route based on actual travel time.
        - Calculates departure suggestions from the requested arrival time.
        """

        import os

        api_key = os.getenv("TOMTOM_API_KEY")

        if not api_key:
            raise ValueError("TOMTOM_API_KEY is not configured")

        # ------------------------------------------------------------
        # Bengaluru locations used by this application
        # ------------------------------------------------------------
        location_coordinates = {
            "Marathahalli Bridge": (12.9566, 77.7010),
            "Silk Board": (12.9172, 77.6228),
            "KR Puram": (13.0070, 77.6950),
            "Hebbal": (13.0358, 77.5970),
            "Whitefield": (12.9698, 77.7499),
            "Electronic City": (12.8452, 77.6602),
        }

        if data.origin not in location_coordinates:
            raise ValueError(f"Unknown origin: {data.origin}")

        if data.destination not in location_coordinates:
            raise ValueError(f"Unknown destination: {data.destination}")

        origin_lat, origin_lon = location_coordinates[data.origin]
        destination_lat, destination_lon = location_coordinates[data.destination]

        # ------------------------------------------------------------
        # Parse the requested arrival time
        # ------------------------------------------------------------
        try:
            requested_arrival = datetime.strptime(
                data.preferred_arrival,
                "%H:%M",
            )
        except ValueError as exc:
            raise ValueError(
                "preferred_arrival must use HH:MM format"
            ) from exc

        now = datetime.now()

        arrival_datetime = now.replace(
            hour=requested_arrival.hour,
            minute=requested_arrival.minute,
            second=0,
            microsecond=0,
        )

        # If the requested time has already passed today, use tomorrow.
        if arrival_datetime <= now:
            arrival_datetime += timedelta(days=1)

        # TomTom accepts an ISO-8601 local date/time for arriveAt.
        arrive_at = arrival_datetime.strftime("%Y-%m-%dT%H:%M:%S")

        # ------------------------------------------------------------
        # TomTom Routing API
        # ------------------------------------------------------------
        route_url = (
            "https://api.tomtom.com/routing/1/"
            f"calculateRoute/"
            f"{origin_lat},{origin_lon}:"
            f"{destination_lat},{destination_lon}/json"
        )

        params = {
            "key": api_key,
            "traffic": "true",
            "routeType": "fastest",
            "travelMode": "car",
            # TomTom's maxAlternatives controls the number of alternatives
            # in addition to the main route.
            "maxAlternatives": 2,
            "arriveAt": arrive_at,
            # Request text guidance so we can extract actual road/street names
            # from the returned route instead of displaying generic labels.
            "instructionsType": "text",
            "language": "en-GB",
        }

        try:
            response = requests.get(
                route_url,
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.exception(
                "TomTom routing request failed for %s -> %s",
                data.origin,
                data.destination,
            )
            raise ValueError(
                "Unable to calculate the commute route right now. "
                "Please check the TomTom API configuration and try again."
            ) from exc
        except ValueError as exc:
            logger.exception("TomTom returned invalid JSON")
            raise ValueError(
                "TomTom returned an invalid routing response."
            ) from exc

        routes = payload.get("routes", [])

        if not isinstance(routes, list) or not routes:
            raise ValueError(
                "TomTom did not return any routes for the selected locations."
            )

        # ------------------------------------------------------------
        # Helpers for route intelligence
        # ------------------------------------------------------------
        def route_status(delay_minutes: float) -> str:
            if delay_minutes <= 3:
                return "LOW"
            if delay_minutes <= 8:
                return "MODERATE"
            if delay_minutes <= 15:
                return "HIGH"
            return "SEVERE"

        def clean_road_name(value: Any) -> str | None:
            """Normalize a TomTom street/road name."""
            if value is None:
                return None

            value = str(value).strip()
            if not value:
                return None

            # Avoid returning generic guidance placeholders as road names.
            ignored = {
                "unknown road",
                "unnamed road",
                "unnamed",
                "unknown",
                "",
            }
            if value.lower() in ignored:
                return None

            return value

        def extract_route_roads(route: Dict[str, Any]) -> List[str]:
            """
            Extract real road/street names from TomTom guidance.

            TomTom guidance instructions expose the street followed after a
            maneuver and may also expose road numbers. We collect the actual
            names, remove duplicates while preserving route order, and keep a
            short list for the dashboard.
            """
            roads: List[str] = []

            guidance = route.get("guidance", {})
            instructions = guidance.get("instructions", [])

            if isinstance(instructions, list):
                for instruction in instructions:
                    if not isinstance(instruction, dict):
                        continue

                    street = clean_road_name(instruction.get("street"))
                    if street:
                        roads.append(street)

                    road_numbers = instruction.get("roadNumbers", [])
                    if isinstance(road_numbers, list):
                        for road_number in road_numbers:
                            road_number = clean_road_name(road_number)
                            if road_number:
                                roads.append(road_number)

                    # Some response variants expose the road as a nested
                    # object. Support those without depending on them.
                    road = instruction.get("road")
                    if isinstance(road, dict):
                        nested_name = clean_road_name(
                            road.get("name") or road.get("street")
                        )
                        if nested_name:
                            roads.append(nested_name)

            # Remove duplicates while preserving the order in which roads
            # appear along the route.
            unique_roads: List[str] = []
            seen = set()

            for road in roads:
                key = road.casefold()
                if key not in seen:
                    seen.add(key)
                    unique_roads.append(road)

            return unique_roads[:8]

        def build_route_name(
            road_names: List[str],
            route_index: int,
        ) -> str:
            """Build a human-readable route identity from real road names."""
            if road_names:
                # Three names are enough to identify the route without making
                # the card excessively long.
                visible_roads = road_names[:3]
                return " → ".join(visible_roads)

            # This is only a fallback when TomTom did not provide guidance
            # street names. We do not pretend to know a road name.
            return (
                "Recommended Route"
                if route_index == 0
                else f"TomTom Alternative {route_index}"
            )

        # ------------------------------------------------------------
        # Normalize actual TomTom routes
        # ------------------------------------------------------------
        normalized_routes: List[Dict[str, Any]] = []

        for index, route in enumerate(routes[:3]):
            if not isinstance(route, dict):
                continue

            summary = route.get("summary", {})
            if not isinstance(summary, dict):
                summary = {}

            travel_time_seconds = int(
                summary.get("travelTimeInSeconds", 0) or 0
            )

            traffic_delay_seconds = int(
                summary.get("trafficDelayInSeconds", 0) or 0
            )

            length_meters = int(
                summary.get("lengthInMeters", 0) or 0
            )

            if travel_time_seconds <= 0:
                logger.warning(
                    "TomTom returned a route without travel time: %s",
                    route,
                )
                continue

            travel_minutes = round(travel_time_seconds / 60, 1)
            delay_minutes = round(max(0, traffic_delay_seconds) / 60, 1)
            distance_km = round(length_meters / 1000, 2)
            status = route_status(delay_minutes)
            road_names = extract_route_roads(route)
            route_name = build_route_name(road_names, index)

            # TomTom can provide actual timestamps. If unavailable, calculate
            # departure from the requested arrival time and route duration.
            tomtom_departure = summary.get("departureTime")
            tomtom_arrival = summary.get("arrivalTime")

            if tomtom_departure:
                departure_time = str(tomtom_departure)[-8:-3]
            else:
                departure_datetime = arrival_datetime - timedelta(
                    minutes=travel_minutes
                )
                departure_time = departure_datetime.strftime("%H:%M")

            if tomtom_arrival:
                actual_arrival_time = str(tomtom_arrival)[-8:-3]
            else:
                actual_arrival_time = data.preferred_arrival

            normalized_routes.append(
                {
                    # IMPORTANT: The frontend already displays route.route,
                    # so route now contains the actual road-based identity.
                    "route": route_name,
                    "route_name": route_name,
                    "road_names": road_names,
                    "type": "Live Traffic Route",
                    "travel_time_minutes": travel_minutes,
                    "estimated_travel_minutes": travel_minutes,
                    "traffic_delay_minutes": delay_minutes,
                    "distance_km": distance_km,
                    "status": status,
                    "departure_time": departure_time,
                    "arrival_time": actual_arrival_time,
                    "recommended": False,
                    "recommended_for": "Alternative route",
                    "typical_delay": (
                        f"{delay_minutes:g} min"
                        if delay_minutes > 0
                        else "No significant delay"
                    ),
                }
            )

        if not normalized_routes:
            raise ValueError(
                "TomTom returned routes, but none contained valid travel-time data."
            )

        # ------------------------------------------------------------
        # Choose the genuinely fastest returned route
        # ------------------------------------------------------------
        best_route = min(
            normalized_routes,
            key=lambda item: item["travel_time_minutes"],
        )

        for route in normalized_routes:
            route["recommended"] = route is best_route

            if route is best_route:
                route["recommended_for"] = "Fastest arrival"
            else:
                time_difference = round(
                    route["travel_time_minutes"]
                    - best_route["travel_time_minutes"],
                    1,
                )
                if time_difference > 0:
                    route["recommended_for"] = (
                        f"{time_difference:g} min slower than recommended"
                    )
                else:
                    route["recommended_for"] = "Alternative route"

        # ------------------------------------------------------------
        # Departure suggestions
        # ------------------------------------------------------------
        departure_suggestions = []

        # These are real departure times derived from the fastest TomTom route.
        # They are not fake 30/45/60-minute durations.
        buffer_minutes = [0, 5, 10]

        for buffer in buffer_minutes:
            departure_datetime = arrival_datetime - timedelta(
                minutes=best_route["travel_time_minutes"] + buffer
            )

            departure_suggestions.append(
                {
                    "departure_time": departure_datetime.strftime("%H:%M"),
                    "estimated_travel_minutes": best_route[
                        "travel_time_minutes"
                    ],
                    "traffic_delay_minutes": best_route[
                        "traffic_delay_minutes"
                    ],
                    "distance_km": best_route["distance_km"],
                    "status": "RECOMMENDED" if buffer == 0 else "BUFFER",
                    "recommended": buffer == 0,
                    "buffer_minutes": buffer,
                }
            )

        # ------------------------------------------------------------
        # Advisory
        # ------------------------------------------------------------
        recommended_departure = departure_suggestions[0]["departure_time"]

        delay_text = (
            f"{best_route['traffic_delay_minutes']:g} min traffic delay"
            if best_route["traffic_delay_minutes"] > 0
            else "no significant traffic delay"
        )

        route_identity = best_route.get("route_name") or "the recommended route"

        advisory = (
            f"Leave at {recommended_departure} to arrive by "
            f"{data.preferred_arrival}. Estimated travel time is "
            f"{best_route['travel_time_minutes']:g} minutes for approximately "
            f"{best_route['distance_km']:g} km, with {delay_text}. "
            f"Recommended via {route_identity}."
        )

        return {
            "origin": data.origin,
            "destination": data.destination,
            "preferred_arrival": data.preferred_arrival,
            "recommended_departure": recommended_departure,
            "departure_suggestions": departure_suggestions,
            "route_alternatives": normalized_routes,
            "recommended_route": best_route,
            "advisory": advisory,
            "source": "TomTom Routing API",
            "traffic_aware": True,
            "route_intelligence": True,
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

# ---------------------------------------------------------------------------
# V2 - Bengaluru Live Traffic Locations
# ---------------------------------------------------------------------------

BENGALURU_TRAFFIC_POINTS = {
    "Marathahalli Bridge": {
        "latitude": 12.9566,
        "longitude": 77.7010,
    },
    "Silk Board": {
        "latitude": 12.9172,
        "longitude": 77.6228,
    },
    "KR Puram": {
        "latitude": 13.0070,
        "longitude": 77.6950,
    },
    "Whitefield": {
        "latitude": 12.9698,
        "longitude": 77.7499,
    },
    "Hebbal": {
        "latitude": 13.0358,
        "longitude": 77.5970,
    },
    "Electronic City": {
        "latitude": 12.8452,
        "longitude": 77.6602,
    },
}

def get_bengaluru_live_traffic():
    """
    Fetch live TomTom traffic for multiple Bengaluru locations.
    """

    results = []

    for location_name, point in BENGALURU_TRAFFIC_POINTS.items():

        try:
            data = get_live_traffic(
                point["latitude"],
                point["longitude"],
            )

            flow = data.get("flowSegmentData", {})

            current_speed = flow.get("currentSpeed", 0)
            free_flow_speed = flow.get("freeFlowSpeed", 0)

            if free_flow_speed > 0:
                speed_ratio = current_speed / free_flow_speed
            else:
                speed_ratio = 0

            if speed_ratio >= 0.80:
                traffic_condition = "Normal"
            elif speed_ratio >= 0.60:
                traffic_condition = "Moderate"
            elif speed_ratio >= 0.40:
                traffic_condition = "Heavy"
            else:
                traffic_condition = "Severe"

            coordinates = flow.get("coordinates", {})
            road_coordinates = coordinates.get("coordinate", [])

            results.append({
                "location": location_name,
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "current_speed_kmph": current_speed,
                "free_flow_speed_kmph": free_flow_speed,
                "speed_ratio": round(speed_ratio, 2),
                "traffic_condition": traffic_condition,
                "confidence": flow.get("confidence"),
                "road_closed": flow.get("roadClosure"),
                "coordinates": road_coordinates,
                "success": True,
            })

        except Exception as exc:
            logger.exception(
                "Failed to fetch TomTom traffic for %s",
                location_name,
            )

            results.append({
                "location": location_name,
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "success": False,
                "error": str(exc),
            })

    return results
