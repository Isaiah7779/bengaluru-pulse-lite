"""
OSRM client for Bengaluru Pulse.

Connects the FastAPI backend to the local OSRM server.

Expected OSRM server:
    http://localhost:5000

Example:
    http://localhost:5000/route/v1/driving/77.7500,12.9698;77.7011,12.9591
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx


logger = logging.getLogger(__name__)


# ============================================================================
# EXCEPTIONS
# ============================================================================


class OSRMError(Exception):
    """Raised when OSRM routing fails."""

    pass


# ============================================================================
# OSRM CLIENT
# ============================================================================


class OSRMClient:
    """
    Async client for the local OSRM routing engine.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        timeout: float = 10.0,
    ) -> None:

        self.base_url = base_url.rstrip("/")

        self.timeout = timeout

    # ------------------------------------------------------------------------
    # Route
    # ------------------------------------------------------------------------

    async def route(
        self,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        *,
        alternatives: bool = True,
        overview: bool = True,
        steps: bool = True,
        profile: str = "driving",
    ) -> Dict[str, Any]:

        """
        Calculate a route through OSRM.

        Coordinates are supplied as:

            latitude, longitude

        OSRM requires:

            longitude, latitude
        """

        # --------------------------------------------------------------------
        # Build coordinate string
        # --------------------------------------------------------------------

        coordinates = (
            f"{origin_lon},{origin_lat};"
            f"{destination_lon},{destination_lat}"
        )

        # --------------------------------------------------------------------
        # Endpoint
        # --------------------------------------------------------------------

        url = (
            f"{self.base_url}"
            f"/route/v1/{profile}/"
            f"{coordinates}"
        )

        # --------------------------------------------------------------------
        # Query parameters
        # --------------------------------------------------------------------

        params = {
            "overview": "full" if overview else "false",
            "steps": "true" if steps else "false",
            "alternatives": "true" if alternatives else "false",
            "geometries": "geojson",
        }

        logger.info(
            "OSRM route request: %s",
            url,
        )

        # --------------------------------------------------------------------
        # HTTP request
        # --------------------------------------------------------------------

        try:

            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    url,
                    params=params,
                )

                response.raise_for_status()

        except httpx.TimeoutException as exc:

            logger.error(
                "OSRM request timed out: %s",
                exc,
            )

            raise OSRMError(
                "OSRM routing request timed out."
            ) from exc

        except httpx.HTTPError as exc:

            logger.error(
                "OSRM HTTP error: %s",
                exc,
            )

            raise OSRMError(
                f"OSRM request failed: {exc}"
            ) from exc

        # --------------------------------------------------------------------
        # Parse JSON
        # --------------------------------------------------------------------

        try:

            payload = response.json()

        except ValueError as exc:

            raise OSRMError(
                "OSRM returned invalid JSON."
            ) from exc

        # --------------------------------------------------------------------
        # Validate OSRM response
        # --------------------------------------------------------------------

        if payload.get("code") != "Ok":

            message = payload.get(
                "message",
                "OSRM did not return a valid route.",
            )

            raise OSRMError(
                str(message)
            )

        routes = payload.get(
            "routes",
            [],
        )

        if not isinstance(
            routes,
            list,
        ) or not routes:

            raise OSRMError(
                "OSRM returned no routes."
            )

        logger.info(
            "OSRM returned %d route(s).",
            len(routes),
        )

        return payload

    # ------------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------------

    async def health(self) -> bool:

        """
        Check whether OSRM is reachable.
        """

        url = (
            f"{self.base_url}/"
        )

        try:

            async with httpx.AsyncClient(
                timeout=3.0
            ) as client:

                response = await client.get(
                    url
                )

            return response.status_code < 500

        except Exception:

            return False


# ============================================================================
# HELPERS
# ============================================================================


def extract_route_geometry(
    route: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    """
    Extract GeoJSON geometry from an OSRM route.
    """

    geometry = route.get(
        "geometry"
    )

    if not geometry:
        return None

    if (
        isinstance(
            geometry,
            dict,
        )
        and geometry.get("type")
        and geometry.get("coordinates")
    ):
        return geometry

    return None


def extract_route_steps(
    route: Dict[str, Any],
) -> List[Dict[str, Any]]:

    """
    Extract normalized turn-by-turn steps.
    """

    result: List[
        Dict[str, Any]
    ] = []

    legs = route.get(
        "legs",
        [],
    )

    if not isinstance(
        legs,
        list,
    ):
        return result

    for leg in legs:

        if not isinstance(
            leg,
            dict,
        ):
            continue

        steps = leg.get(
            "steps",
            [],
        )

        if not isinstance(
            steps,
            list,
        ):
            continue

        for step in steps:

            if not isinstance(
                step,
                dict,
            ):
                continue

            maneuver = step.get(
                "maneuver",
                {},
            )

            instruction = None

            if isinstance(
                maneuver,
                dict,
            ):
                instruction = (
                    maneuver.get(
                        "instruction"
                    )
                    or maneuver.get(
                        "type"
                    )
                )

            result.append(
                {
                    "name": (
                        step.get(
                            "name"
                        )
                        or ""
                    ),
                    "distance_m": float(
                        step.get(
                            "distance",
                            0,
                        )
                        or 0
                    ),
                    "duration_s": float(
                        step.get(
                            "duration",
                            0,
                        )
                        or 0
                    ),
                    "instruction": instruction,
                }
            )

    return result