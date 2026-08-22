"""FastAPI application for Bengaluru Pulse traffic intelligence."""

import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import database
from domain import LOCATION_META, WEATHER_ALIASES
from schemas import (
    CommuteInput,
    ForecastInput,
    LocationsResponse,
    TrafficInput,
)
from services import (
    IncidentService,
    ModelBundle,
    TrafficService,
    get_live_traffic,
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application configuration
# ---------------------------------------------------------------------------

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Services and ML model
# ---------------------------------------------------------------------------

try:
    model_bundle = ModelBundle(settings)
except Exception:
    logger.exception("Failed to load ML artifacts")
    raise

traffic_service = TrafficService()
incident_service = IncidentService(settings)


# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------

@app.get("/")
def home() -> dict:
    """API health and endpoint discovery."""

    return {
        "message": "Bengaluru Pulse Intelligence API",
        "version": settings.app_version,
        "status": "running",
        "endpoints": [
            "/health",
            "/locations",
            "/predict",
            "/history",
            "/dashboard",
            "/database-analytics",
            "/forecast",
            "/hotspots",
            "/analytics",
            "/commute-advisor",
            "/historical-trends",
            "/incidents",
            "/docs",
        ],
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Return API and model health status."""

    return {
        "status": "ok",
        "model_loaded": model_bundle.model is not None,
        "database": "connected",
    }


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@app.get("/locations", response_model=LocationsResponse)
def get_locations() -> dict:
    """Return supported prediction locations."""

    return {
        "locations": [
            {
                "name": name,
                "lat": meta["lat"],
                "lon": meta["lon"],
                "description": meta["description"],
            }
            for name, meta in LOCATION_META.items()
        ]
    }


# ---------------------------------------------------------------------------
# ML Prediction
# ---------------------------------------------------------------------------

@app.post("/predict")
def predict(data: TrafficInput) -> dict:
    """
    Predict traffic congestion using the trained ML model.

    Successful predictions are stored in SQLite by the ModelBundle.
    """

    try:
        result = model_bundle.predict(data)

        logger.info(
            "Prediction completed | location=%s | congestion=%s",
            data.location,
            result.get("predicted_congestion"),
        )

        return result

    except ValueError as exc:
        logger.warning("Invalid prediction input: %s", exc)

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Prediction failed")

        raise HTTPException(
            status_code=500,
            detail="Prediction failed",
        ) from exc


# ---------------------------------------------------------------------------
# Prediction history
# ---------------------------------------------------------------------------

@app.get("/history")
def history() -> dict:
    """Return prediction history stored in SQLite."""

    try:
        records = database.get_history()

        return {
            "count": len(records),
            "predictions": records,
        }

    except Exception as exc:
        logger.exception("Failed to retrieve prediction history")

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve prediction history",
        ) from exc


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/dashboard")
def dashboard() -> dict:
    """Return database-driven dashboard information."""

    try:
        analytics_data = database.analytics()
        history_data = database.get_history()

        return {
            "analytics": analytics_data,
            "recent_predictions": history_data[:10],
        }

    except Exception as exc:
        logger.exception("Failed to generate dashboard data")

        raise HTTPException(
            status_code=500,
            detail="Unable to generate dashboard data",
        ) from exc


# ---------------------------------------------------------------------------
# Database analytics
# ---------------------------------------------------------------------------

@app.get("/database-analytics")
def database_analytics() -> dict:
    """Return analytics calculated from stored predictions."""

    try:
        return database.analytics()

    except Exception as exc:
        logger.exception("Failed to calculate database analytics")

        raise HTTPException(
            status_code=500,
            detail="Unable to calculate analytics",
        ) from exc


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

@app.post("/forecast")
def forecast(data: ForecastInput) -> dict:
    """Return a 12-hour congestion forecast for one location."""

    try:
        return traffic_service.forecast(data)

    except Exception as exc:
        logger.exception("Forecast failed")

        raise HTTPException(
            status_code=500,
            detail="Forecast generation failed",
        ) from exc


# ---------------------------------------------------------------------------
# Traffic hotspots
# ---------------------------------------------------------------------------

@app.get("/hotspots")
def hotspots(
    weather: str = Query("Sunny"),
) -> dict:
    """Return current congestion estimates for supported locations."""

    if weather not in WEATHER_ALIASES:
        raise HTTPException(
            status_code=422,
            detail="Invalid weather condition",
        )

    try:
        return traffic_service.hotspots(weather)

    except Exception as exc:
        logger.exception("Hotspot calculation failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to calculate traffic hotspots",
        ) from exc


# ---------------------------------------------------------------------------
# Traffic analytics
# ---------------------------------------------------------------------------

@app.get("/analytics")
def analytics(
    location: str = Query("Silk Board"),
    weather: str = Query("Sunny"),
) -> dict:
    """Return daily and weekly analytics for one location."""

    if location not in LOCATION_META:
        raise HTTPException(
            status_code=422,
            detail="Invalid location",
        )

    if weather not in WEATHER_ALIASES:
        raise HTTPException(
            status_code=422,
            detail="Invalid weather condition",
        )

    try:
        return traffic_service.analytics(
            location,
            weather,
        )

    except Exception as exc:
        logger.exception("Analytics generation failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to generate analytics",
        ) from exc


# ---------------------------------------------------------------------------
# Commute advisor
# ---------------------------------------------------------------------------

@app.post("/commute-advisor")
def commute_advisor(data: CommuteInput) -> dict:
    """Recommend departure times and route alternatives."""

    try:
        return traffic_service.commute_advisor(data)

    except Exception as exc:
        logger.exception("Commute advisor failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to generate commute advice",
        ) from exc


# ---------------------------------------------------------------------------
# Historical trends
# ---------------------------------------------------------------------------

@app.get("/historical-trends")
def historical_trends(
    weather: str = Query("Sunny"),
) -> dict:
    """Return simulated seven-day historical congestion trends."""

    if weather not in WEATHER_ALIASES:
        raise HTTPException(
            status_code=422,
            detail="Invalid weather condition",
        )

    try:
        return traffic_service.historical_trends(weather)

    except Exception as exc:
        logger.exception("Historical trend generation failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to generate historical trends",
        ) from exc


# ---------------------------------------------------------------------------
# Traffic incidents
# ---------------------------------------------------------------------------

@app.get("/incidents")
def incidents() -> dict:
    """Return traffic incidents from the configured feed."""

    try:
        return incident_service.fetch_incidents()

    except Exception as exc:
        logger.exception("Incident service failed")

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve traffic incidents",
        ) from exc
        
# ---------------------------------------------------------------------------
# TomTom Live Traffic
# ---------------------------------------------------------------------------

@app.get("/api/live-traffic")
def live_traffic(
    latitude: float = Query(..., description="Latitude"),
    longitude: float = Query(..., description="Longitude"),
) -> dict:
    """Get live traffic data for the road segment nearest to a coordinate."""

    try:
        data = get_live_traffic(latitude, longitude)

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

        return {
    "success": True,
    "latitude": latitude,
    "longitude": longitude,
    "current_speed_kmph": current_speed,
    "free_flow_speed_kmph": free_flow_speed,
    "speed_ratio": round(speed_ratio, 2),
    "traffic_condition": traffic_condition,
    "current_travel_time_seconds": flow.get("currentTravelTime"),
    "free_flow_travel_time_seconds": flow.get("freeFlowTravelTime"),
    "confidence": flow.get("confidence"),
    "road_closed": flow.get("roadClosure"),
    "coordinates": flow.get("coordinates"),
}

    except Exception as exc:
        logger.exception("TomTom live traffic request failed")
        raise HTTPException(
            status_code=502,
            detail=f"Unable to retrieve live traffic data: {exc}",
        )