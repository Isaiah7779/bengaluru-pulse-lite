"""V1 endpoints kept for backward compatibility.

Endpoints that used to return simulated data now either serve collected
observations or return 410 Gone with a pointer to the replacement.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.deps import settings_dep
from core.errors import AppError, UpstreamUnavailable
from core.settings import Settings
from database import database
from db.session import get_db
from domain import LOCATION_META
from providers.tomtom import ProviderError, ProviderUnavailable, TomTomProvider
from schemas import LocationsResponse, TrafficInput
from traffic.state_engine import active_incidents, congestion_level, latest_segment_state

logger = logging.getLogger(__name__)
router = APIRouter(tags=["legacy"])

_bundle = None
_bundle_error: Optional[str] = None


def model_bundle(settings: Settings):
    global _bundle, _bundle_error
    if _bundle is None and _bundle_error is None:
        try:
            from services import ModelBundle

            _bundle = ModelBundle(settings)
        except Exception as exc:  # missing artifacts must not take the API down
            logger.exception("Legacy model unavailable")
            _bundle_error = str(exc)
    return _bundle


@router.get("/")
def home(settings: Settings = Depends(settings_dep)):
    return {
        "message": "Bengaluru Pulse API",
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "health": ["/health", "/health/ready"],
    }


@router.get("/locations", response_model=LocationsResponse)
def get_locations():
    return {
        "locations": [
            {"name": n, "lat": m["lat"], "lon": m["lon"], "description": m["description"]}
            for n, m in LOCATION_META.items()
        ]
    }


@router.post("/predict")
def predict(data: TrafficInput, settings: Settings = Depends(settings_dep)):
    bundle = model_bundle(settings)
    if bundle is None:
        raise UpstreamUnavailable("Legacy model artifacts are not available", code="model_unavailable")
    try:
        return bundle.predict(data)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_input", status_code=422) from exc


@router.get("/history")
def history():
    records = database.get_history()
    return {"count": len(records), "predictions": records, "legacy": True}


@router.get("/dashboard")
def dashboard():
    return {"analytics": database.analytics(), "recent_predictions": database.get_history(10), "legacy": True}


@router.get("/database-analytics")
def database_analytics():
    return database.analytics()


@router.get("/hotspots")
def hotspots(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    """Current congestion at monitored points, from collected TomTom observations."""

    segments = latest_segment_state(db, settings.observation_stale_minutes)
    items = [
        {
            "location": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "status": s["observation"]["congestion"],
            "speed_ratio": s["observation"]["speed_ratio"],
            "current_speed_kmph": s["observation"]["current_speed_kmph"],
            "observed_at": s["observation"]["observed_at"],
        }
        for s in segments
        if s["status"] == "fresh"
    ]
    items.sort(key=lambda x: x["speed_ratio"])
    return {
        "source": "TomTom Traffic Flow (collected)",
        "hotspots": items,
        "fresh_points": len(items),
        "monitored_points": len(segments),
        "worst_location": items[0]["location"] if items else None,
    }


@router.get("/incidents")
def incidents_legacy(db: Session = Depends(get_db)):
    rows = active_incidents(db, limit=200)
    return {
        "source": "TomTom Traffic Incidents (collected)",
        "status": "ok" if rows else "no_data",
        "count": len(rows),
        "incidents": [
            {
                "location_name": " → ".join(filter(None, [r.road_from, r.road_to])) or f"{r.lat:.4f},{r.lon:.4f}",
                "severity": {None: "UNKNOWN", 0: "UNKNOWN", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "HIGH"}.get(r.severity, "UNKNOWN"),
                "disruption_type": r.category.replace("_", " ").title(),
                "description": r.description,
                "lat": r.lat,
                "lon": r.lon,
                "source": r.source,
            }
            for r in rows
        ],
    }


@router.get("/api/live-traffic")
async def live_traffic(
    latitude: float = Query(..., ge=12.5, le=13.5),
    longitude: float = Query(..., ge=77.2, le=78.0),
    settings: Settings = Depends(settings_dep),
):
    """Live TomTom flow at one point (counts against the daily quota)."""

    try:
        reading = await TomTomProvider(settings).flow_segment(latitude, longitude)
    except ProviderUnavailable as exc:
        raise UpstreamUnavailable(str(exc), code="traffic_unavailable") from exc
    except ProviderError as exc:
        raise UpstreamUnavailable(str(exc), code="traffic_provider_error") from exc
    return {
        "success": True,
        "latitude": latitude,
        "longitude": longitude,
        "current_speed_kmph": reading.current_speed_kmph,
        "free_flow_speed_kmph": reading.free_flow_speed_kmph,
        "speed_ratio": round(reading.speed_ratio, 2),
        "traffic_condition": congestion_level(reading.speed_ratio, reading.road_closure),
        "current_travel_time_seconds": reading.current_travel_time_s,
        "free_flow_travel_time_seconds": reading.free_flow_travel_time_s,
        "confidence": reading.confidence,
        "road_closed": reading.road_closure,
        "fetched_at": reading.fetched_at.isoformat(),
        "source": "tomtom",
    }


@router.get("/api/live-traffic/bengaluru")
def bengaluru_live_traffic(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    """Latest collected observation per monitored point (no provider fan-out per request)."""

    segments = latest_segment_state(db, settings.observation_stale_minutes)
    traffic = []
    for s in segments:
        obs = s["observation"]
        item = {"location": s["name"], "latitude": s["lat"], "longitude": s["lon"], "status": s["status"]}
        if obs:
            item.update(
                success=True,
                current_speed_kmph=obs["current_speed_kmph"],
                free_flow_speed_kmph=obs["free_flow_speed_kmph"],
                speed_ratio=obs["speed_ratio"],
                traffic_condition=obs["congestion"],
                observed_at=obs["observed_at"],
                coordinates=(s["geometry"] or {}).get("coordinates", []),
            )
        else:
            item.update(success=False, error="no observation collected yet")
        traffic.append(item)
    return {
        "success": True,
        "total_locations": len(traffic),
        "successful_locations": sum(1 for t in traffic if t.get("success")),
        "traffic": traffic,
    }


def _gone(replacement: str):
    return JSONResponse(
        status_code=410,
        content={
            "error": {
                "code": "gone",
                "message": "This endpoint returned simulated data and has been removed. "
                f"Use {replacement} instead.",
            }
        },
    )


@router.api_route("/forecast", methods=["GET", "POST"], include_in_schema=False)
def forecast_gone():
    return _gone("/v1/forecast/models and /v1/forecast/segments/{id}")


@router.get("/analytics", include_in_schema=False)
def analytics_gone():
    return _gone("/v1/traffic/segments/{id}/history")


@router.get("/historical-trends", include_in_schema=False)
def trends_gone():
    return _gone("/v1/traffic/segments/{id}/history")


@router.post("/commute-advisor", include_in_schema=False)
def commute_gone():
    return _gone("POST /v1/routes with depart_at")
