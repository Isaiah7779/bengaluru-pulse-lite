"""Route planning endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import optional_user, settings_dep
from core.errors import AppError
from core.settings import Settings
from db.models import Trip, User
from db.session import get_db
from routing.engine import RoutingEngine
from routing.route_profiles import all_vehicle_metadata
from routing.schemas import (
    RouteRequest,
    RouteRequestV2,
    RouteResponse,
    RouteResponseV2,
    RouteResult,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["routing"])

_engine: Optional[RoutingEngine] = None


def get_engine(settings: Settings = Depends(settings_dep)) -> RoutingEngine:
    global _engine
    if _engine is None:
        from forecasting.predictor import forecast_lookup

        _engine = RoutingEngine(settings, forecast_lookup=forecast_lookup())
    return _engine


def reset_engine() -> None:
    global _engine
    _engine = None


@router.get("/v1/vehicles")
def vehicles(settings: Settings = Depends(settings_dep)):
    """Vehicle modes, the graph serving each, and whether it is available."""

    return {"vehicles": all_vehicle_metadata(settings)}


@router.post("/v1/routes", response_model=RouteResponseV2)
async def plan_route(
    body: RouteRequestV2,
    engine: RoutingEngine = Depends(get_engine),
    user: Optional[User] = Depends(optional_user),
    db: Session = Depends(get_db),
):
    result = await engine.plan(body)
    if body.save_trip:
        if user is None:
            raise AppError("Sign in to save trips to your history", code="auth_required", status_code=401)
        best = next(r for r in result.routes if r.recommended)
        trip = Trip(
            user_id=user.id,
            origin_label=body.origin.label,
            origin_lat=body.origin.lat,
            origin_lon=body.origin.lon,
            destination_label=body.destination.label,
            destination_lat=body.destination.lat,
            destination_lon=body.destination.lon,
            vehicle=body.vehicle.value,
            preference=result.preference_applied.value,
            depart_at=result.depart_at,
            chosen_route={
                "route_id": best.id,
                "distance_m": best.distance_m,
                "eta_s": best.eta_s,
                "eta_basis": best.eta_basis,
                "classification": best.classification.get("type"),
                "summary": best.summary,
                "routes_compared": len(result.routes),
            },
        )
        db.add(trip)
        db.commit()
        result.trip_id = trip.id
    return result


@router.post("/routing/route", response_model=RouteResponse, deprecated=True)
async def legacy_route(body: RouteRequest, engine: RoutingEngine = Depends(get_engine)):
    """V1 route endpoint kept for older clients; served by the V2 engine."""

    v2 = await engine.plan(
        RouteRequestV2(
            origin={"lat": body.origin.lat, "lon": body.origin.lon},
            destination={"lat": body.destination.lat, "lon": body.destination.lon},
            vehicle=body.vehicle,
            max_routes=5 if body.alternatives else 1,
            include_steps=body.steps,
        )
    )
    routes = []
    for r in v2.routes:
        live = r.traffic.eta_s / 60 if r.traffic else None
        routes.append(
            RouteResult(
                route_id=r.id,
                distance_m=r.distance_m,
                duration_s=r.free_flow_duration_s,
                distance_km=round(r.distance_m / 1000, 3),
                duration_min=round(r.free_flow_duration_s / 60, 2),
                geometry=r.geometry if body.overview else None,
                summary=r.summary,
                steps=r.steps,
                live_eta_min=round(live, 2) if live else None,
                base_eta_min=round(r.free_flow_duration_s / 60, 2),
                traffic_delay_min=round(r.traffic.traffic_delay_s / 60, 2) if r.traffic else None,
                traffic_source=r.traffic.source if r.traffic else "OSRM",
                route_score=r.score,
                recommended=r.recommended,
                intelligence_available=r.traffic is not None,
                route_type="regular" if r.is_reference else r.classification.get("type", "alternative"),
                route_reason=r.classification.get("reason", ""),
            )
        )
    return RouteResponse(
        source="osrm+tomtom" if any(r.intelligence_available for r in routes) else "osrm",
        vehicle=body.vehicle,
        routes=routes,
        intelligence={"comparison_basis": v2.comparison_basis, "vehicle_profile": v2.vehicle_profile},
    )
