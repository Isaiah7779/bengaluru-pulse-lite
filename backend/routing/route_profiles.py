"""Vehicle modes and the routing graph that genuinely serves each one.

Each OSRM server is built from one Lua profile (infrastructure/osrm/build_osrm.sh):

    car      -> car.lua      (OSRM_URL)
    walk     -> foot.lua     (OSRM_FOOT_URL)
    bicycle  -> bicycle.lua  (OSRM_BICYCLE_URL)

OSRM ignores the profile name in the request URL, so asking a car server for
"foot" silently returns car routes. Modes are therefore mapped to *servers*, and
a mode whose server is not configured is reported unavailable — never served
by another graph.

Motorcycle: OSRM ships no motorcycle profile. Motorcycles are routed on the car
graph and this is disclosed in every response (`profile_status`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from core.settings import Settings


@dataclass(frozen=True)
class VehicleProfile:
    vehicle: str
    osrm_profile: str  # key used to look up the server URL
    lua_profile: str
    profile_status: str  # dedicated | car_graph_approximation
    tomtom_travel_mode: Optional[str]  # None = traffic not applicable
    excludable: tuple  # OSRM exclude classes supported by the Lua profile
    notes: str


PROFILES: Dict[str, VehicleProfile] = {
    "car": VehicleProfile(
        "car", "driving", "car.lua", "dedicated", "car", ("toll", "motorway", "ferry"),
        "OSRM car profile on the full Bengaluru OSM graph.",
    ),
    "motorcycle": VehicleProfile(
        "motorcycle", "driving", "car.lua", "car_graph_approximation", "motorcycle", ("toll", "motorway", "ferry"),
        "No OSRM motorcycle profile exists; routed on the car graph. Two-wheeler-specific "
        "restrictions (e.g. flyovers or expressways closed to two-wheelers) are not modelled.",
    ),
    "bicycle": VehicleProfile(
        "bicycle", "cycling", "bicycle.lua", "dedicated", None, (),
        "OSRM bicycle profile (uses cycle-permitted ways, cycling speeds).",
    ),
    "walk": VehicleProfile(
        "walk", "foot", "foot.lua", "dedicated", None, (),
        "OSRM foot profile (footways, pedestrian access, walking speed ~5 km/h).",
    ),
}

SUPPORTED_VEHICLES = set(PROFILES)


def get_profile(vehicle: str) -> VehicleProfile:
    key = str(getattr(vehicle, "value", vehicle)).strip().lower()
    if key not in PROFILES:
        raise ValueError(f"Unsupported vehicle: {key}")
    return PROFILES[key]


def get_osrm_profile(vehicle: str) -> str:
    return get_profile(vehicle).osrm_profile


def server_url(settings: Settings, vehicle: str) -> Optional[str]:
    return settings.osrm_url_for(get_profile(vehicle).osrm_profile)


def get_vehicle_metadata(vehicle: str, settings: Optional[Settings] = None) -> Dict[str, object]:
    profile = get_profile(vehicle)
    data: Dict[str, object] = {
        "vehicle": profile.vehicle,
        "osrm_profile": profile.osrm_profile,
        "lua_profile": profile.lua_profile,
        "profile_status": profile.profile_status,
        "traffic_supported": profile.tomtom_travel_mode is not None,
        "avoid_options": list(profile.excludable),
        "notes": profile.notes,
    }
    if settings is not None:
        data["available"] = bool(server_url(settings, vehicle))
    return data


def all_vehicle_metadata(settings: Settings) -> List[Dict[str, object]]:
    return [get_vehicle_metadata(v, settings) for v in PROFILES]
