from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class VehicleMode(str, Enum):
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    BICYCLE = "bicycle"
    WALK = "walk"


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate

    vehicle: VehicleMode = VehicleMode.CAR

    alternatives: bool = True
    overview: bool = True
    steps: bool = True


class RouteStep(BaseModel):
    name: str = ""
    distance_m: float = 0.0
    duration_s: float = 0.0
    instruction: Optional[str] = None


class RouteResult(BaseModel):
    route_id: str

    distance_m: float
    duration_s: float

    distance_km: float
    duration_min: float

    geometry: Optional[dict] = None

    summary: str = ""

    steps: List[RouteStep] = Field(
        default_factory=list
    )

    # ---------------------------------------------------------
    # Bengaluru Pulse intelligence
    # ---------------------------------------------------------

    live_eta_min: Optional[float] = None

    base_eta_min: Optional[float] = None

    traffic_delay_min: Optional[float] = None

    traffic_status: Optional[str] = None

    traffic_ratio: Optional[float] = None

    traffic_source: Optional[str] = None

    route_score: Optional[float] = None

    recommended: bool = False

    intelligence_available: bool = False
    
    route_type: str = "alternative"
    route_reason: str = ""


class RouteResponse(BaseModel):
    source: str

    vehicle: VehicleMode

    routes: List[RouteResult]

    intelligence: Optional[dict] = None