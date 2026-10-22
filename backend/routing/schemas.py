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

# ===========================================================================
# V2 routing API (/v1/routes)
# ===========================================================================

from datetime import datetime  # noqa: E402
from typing import Any, Dict, Literal  # noqa: E402


class RoutePreference(str, Enum):
    FASTEST = "fastest"
    SHORTEST = "shortest"
    LEAST_TRAFFIC_NOW = "least_traffic_now"
    LEAST_TRAFFIC_PREDICTED = "least_traffic_predicted"
    BALANCED = "balanced"


class AvoidOption(str, Enum):
    TOLL = "toll"
    MOTORWAY = "motorway"
    FERRY = "ferry"


class Place(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    label: Optional[str] = Field(None, max_length=200)


class RouteRequestV2(BaseModel):
    origin: Place
    destination: Place
    vehicle: VehicleMode = VehicleMode.CAR
    preference: RoutePreference = RoutePreference.FASTEST
    depart_at: Optional[datetime] = Field(
        None, description="Departure time (ISO 8601 with offset). Omit for 'now'."
    )
    avoid: List[AvoidOption] = Field(default_factory=list, max_length=1)
    max_routes: int = Field(5, ge=1, le=8)
    include_steps: bool = True
    save_trip: bool = False


class TrafficTiming(BaseModel):
    source: str
    basis: Literal["traffic_live", "traffic_predicted"]
    eta_s: float
    traffic_delay_s: float
    no_traffic_s: Optional[float] = None
    historic_s: Optional[float] = None
    live_s: Optional[float] = None
    provider_length_m: float
    length_match_pct: float
    depart_at: Optional[datetime] = None
    arrive_at: Optional[datetime] = None


class RouteIncident(BaseModel):
    id: int
    category: str
    severity: Optional[int]
    description: Optional[str]
    road: Optional[str]
    lat: float
    lon: float
    distance_from_route_m: float
    source: str


class RouteSegmentEvidence(BaseModel):
    segment_id: int
    name: str
    congestion: Optional[str]
    speed_ratio: Optional[float]
    current_speed_kmph: Optional[float]
    observed_at: Optional[datetime]
    age_minutes: Optional[float]
    forecast: Optional[Dict[str, Any]] = None


class RouteOption(BaseModel):
    id: str
    rank: int
    is_reference: bool
    recommended: bool
    origin_kind: str  # osrm_primary | osrm_alternative | corridor
    distance_m: float
    free_flow_duration_s: float
    eta_s: float
    eta_basis: str  # traffic_live | traffic_predicted | free_flow
    comparable: bool
    traffic: Optional[TrafficTiming] = None
    traffic_note: Optional[str] = None
    classification: Dict[str, Any]
    score: Optional[float] = None
    score_components: Dict[str, float] = Field(default_factory=dict)
    incidents: List[RouteIncident] = Field(default_factory=list)
    monitored_segments: List[RouteSegmentEvidence] = Field(default_factory=list)
    explanation: List[str] = Field(default_factory=list)
    summary: str = ""
    geometry: Dict[str, Any]
    steps: List[RouteStep] = Field(default_factory=list)


class DataSourceStatus(BaseModel):
    name: str
    status: str  # ok | unavailable | not_applicable | degraded | not_configured
    detail: str = ""
    as_of: Optional[datetime] = None


class RouteResponseV2(BaseModel):
    vehicle: VehicleMode
    vehicle_profile: Dict[str, Any]
    preference_requested: RoutePreference
    preference_applied: RoutePreference
    preference_note: Optional[str] = None
    depart_at: datetime
    departure_mode: Literal["now", "future"]
    comparison_basis: str
    reference_route_id: str
    reference_description: str
    recommended_route_id: str
    recommendation: str
    routes: List[RouteOption]
    weather: Optional[Dict[str, Any]] = None
    data_sources: List[DataSourceStatus]
    warnings: List[str] = Field(default_factory=list)
    candidates_considered: int
    trip_id: Optional[int] = None
