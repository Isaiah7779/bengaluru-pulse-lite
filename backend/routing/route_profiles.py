"""
Vehicle routing profiles.

IMPORTANT:
The current local OSRM server uses the standard OSRM car profile.

Therefore motorcycle/bicycle/walking are currently accepted by the API
interface but must NOT be falsely represented as dedicated OSRM profiles.

Until dedicated OSRM profiles are built, they fall back to driving.
"""

from __future__ import annotations

from typing import Dict


# ============================================================================
# SUPPORTED VEHICLES
# ============================================================================

SUPPORTED_VEHICLES = {
    "car",
    "motorcycle",
    "bicycle",
    "walk",
}


# ============================================================================
# OSRM PROFILE
# ============================================================================

def get_osrm_profile(
    vehicle: str,
) -> str:

    """
    Return the OSRM profile currently available.

    At this stage the Bengaluru Pulse OSRM instance was built with:

        /opt/car.lua

    Therefore all routing currently uses the driving profile.
    """

    vehicle = (
        str(vehicle)
        .strip()
        .lower()
    )

    if vehicle not in SUPPORTED_VEHICLES:

        raise ValueError(
            f"Unsupported vehicle: {vehicle}"
        )

    # ------------------------------------------------------------------------
    # CURRENT IMPLEMENTATION
    # ------------------------------------------------------------------------
    #
    # OSRM was built using car.lua.
    #
    # Do not pretend that this is bicycle/walking/motorcycle-specific routing.
    #

    return "driving"


# ============================================================================
# VEHICLE METADATA
# ============================================================================


def get_vehicle_metadata(
    vehicle: str,
) -> Dict[str, str]:

    vehicle = (
        str(vehicle)
        .strip()
        .lower()
    )

    if vehicle not in SUPPORTED_VEHICLES:

        raise ValueError(
            f"Unsupported vehicle: {vehicle}"
        )

    return {
        "vehicle": vehicle,
        "osrm_profile": get_osrm_profile(
            vehicle
        ),
        "profile_status": (
            "dedicated"
            if vehicle == "car"
            else "fallback_to_car"
        ),
    }