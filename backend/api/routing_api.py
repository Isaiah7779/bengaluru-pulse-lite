"""Route planning endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.deps import optional_user, settings_dep
from core.errors import AppError, UpstreamUnavailable
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

# The engine itself finishes ASSEMBLY_MARGIN_S before the deadline; this outer limit (the
# deadline itself) only catches a bug or an unexpectedly slow CPU step.
SAFETY_NET_S = 0.0

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


def request_deadline(request: Request, settings: Settings = Depends(settings_dep)) -> float:
    """Request deadline, measured from arrival (set by the request-ID middleware, before sign-in)."""

    received = getattr(request.state, "received_at", None) or time.monotonic()
    return received + settings.route_plan_deadline_s


async def _plan_within(engine: RoutingEngine, body: RouteRequestV2, deadline: float) -> RouteResponseV2:
    """Run the engine under the request deadline; the engine bounds itself, this is the safety net."""

    try:
        return await asyncio.wait_for(engine.plan(body, deadline_at=deadline),
                                      timeout=max(0.1, deadline - time.monotonic() + SAFETY_NET_S))
    except asyncio.TimeoutError as exc:
        raise UpstreamUnavailable(
            "Route planning did not finish within the request time limit. This is usually temporary; please try again.",
            code="routing_deadline_exceeded",
        ) from exc


def _save_trip(db: Session, trip: Trip, deadline: float) -> Optional[str]:
    """Insert the trip with a statement timeout bounded by the request deadline; returns a warning on failure."""

    try:
        if db.get_bind().dialect.name == "postgresql":
            seconds = max(0.5, deadline - time.monotonic())
            db.execute(text(f"SET LOCAL statement_timeout = {int(seconds * 1000)}"))
        db.add(trip)
        db.commit()
        return None
    except Exception:
        logger.exception("Saving the trip failed")
        db.rollback()
        return "The route was planned but the trip could not be saved to your history in time; please try again."


@router.post("/v1/routes", response_model=RouteResponseV2)
async def plan_route(
    body: RouteRequestV2,
    deadline: float = Depends(request_deadline),
    engine: RoutingEngine = Depends(get_engine),
    user: Optional[User] = Depends(optional_user),
    db: Session = Depends(get_db),
):
    result = await _plan_within(engine, body, deadline)
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
        problem = _save_trip(db, trip, deadline)
        if problem:
            result.warnings.append(problem)
        else:
            result.trip_id = trip.id
    return result


@router.post("/routing/route", response_model=RouteResponse, deprecated=True)
async def legacy_route(body: RouteRequest, deadline: float = Depends(request_deadline),
                       engine: RoutingEngine = Depends(get_engine)):
    """V1 route endpoint kept for older clients; served by the V2 engine."""

    v2 = await _plan_within(
        engine,
        RouteRequestV2(
            origin={"lat": body.origin.lat, "lon": body.origin.lon},
            destination={"lat": body.destination.lat, "lon": body.destination.lon},
            vehicle=body.vehicle,
            max_routes=5 if body.alternatives else 1,
            include_steps=body.steps,
        ),
        deadline,
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
