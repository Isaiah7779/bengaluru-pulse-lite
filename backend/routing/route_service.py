"""
Bengaluru Pulse intelligent routing service.

Routing architecture:

    Frontend
        |
        v
    FastAPI /routing/route
        |
        v
    RoutingService
        |
        +----> Local OSRM
        |
        +----> Optional TomTom live traffic
        |
        v
    RouteResponse

OSRM is the authoritative route geometry/base route engine.
TomTom is optional live-traffic intelligence.

Automatic route candidates are generated without hardcoding Bengaluru
road names: geographic corridor waypoints are created between origin
and destination, then OSRM snaps those points to the actual OSM road
network.
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from .osrm_client import (
    OSRMClient,
    OSRMError,
    extract_route_geometry,
    extract_route_steps,
)
from .route_profiles import (
    get_osrm_profile,
    get_vehicle_metadata,
)
from .schemas import (
    RouteRequest,
    RouteResponse,
    RouteResult,
    RouteStep,
)

logger = logging.getLogger(__name__)


class RoutingService:
    """
    Main routing orchestration service.

    OSRM provides:
        - route geometry
        - base ETA
        - distance
        - turn-by-turn steps

    TomTom provides, when configured:
        - live traffic ETA
        - traffic delay

    The service first requests the normal OSRM route, then automatically
    explores several geographic corridors. No Bengaluru road names are
    hardcoded into the routing logic.
    """

    def __init__(
        self,
        osrm_url: Optional[str] = None,
    ) -> None:
        # OSRM_URL lets Docker Compose point at the internal osrm service.
        self.osrm_base_url = (
            osrm_url
            or os.getenv("OSRM_URL", "http://localhost:5000")
        ).rstrip("/")

        self.osrm = OSRMClient(
            base_url=self.osrm_base_url,
            timeout=10.0,
        )

        # Settings has no TomTom field; read the key like services.py does.
        self.tomtom_api_key = (
            os.getenv("TOMTOM_API_KEY", "").strip() or None
        )

        self.tomtom_base_url = (
            "https://api.tomtom.com/routing/1/calculateRoute"
        )

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def calculate_route(
        self,
        request: RouteRequest,
    ) -> RouteResponse:
        """
        Calculate multiple automatically discovered route candidates.

        The normal route is always requested first.

        Additional candidates are created using lateral corridor points
        between origin and destination. OSRM then snaps those points onto
        legal OSM roads and calculates the actual route.

        TomTom is optional and must never prevent OSRM routing from working.
        """

        # --------------------------------------------------------------------
        # Vehicle
        # --------------------------------------------------------------------

        vehicle = str(
            request.vehicle.value
            if hasattr(request.vehicle, "value")
            else request.vehicle
        ).lower()

        # Keep this call because route_profiles may perform validation or
        # provide metadata used by the application.
        vehicle_metadata = get_vehicle_metadata(vehicle)
        _ = vehicle_metadata

        osrm_profile = get_osrm_profile(vehicle)

        # --------------------------------------------------------------------
        # Coordinates
        # --------------------------------------------------------------------

        origin_lat = float(request.origin.lat)
        origin_lon = float(request.origin.lon)
        destination_lat = float(request.destination.lat)
        destination_lon = float(request.destination.lon)

        logger.info(
            "Calculating route: %s,%s -> %s,%s | vehicle=%s | profile=%s",
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
            vehicle,
            osrm_profile,
        )

        # ====================================================================
        # 1. NORMAL OSRM ROUTE
        # ====================================================================

        try:
            direct_payload = await self.osrm.route(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
                alternatives=request.alternatives,
                overview=request.overview,
                steps=request.steps,
                profile=osrm_profile,
            )
        except Exception:
            logger.exception("Normal OSRM route request failed.")
            raise

        osrm_routes: List[Dict[str, Any]] = list(
            direct_payload.get("routes", []) or []
        )
        if not osrm_routes:
            raise OSRMError("OSRM returned no routes.")

        # Preserve the original direct OSRM route as the reference route.
        # All shortcut/longcut classification is relative to this route.
        reference_route: Dict[str, Any] = osrm_routes[0]

        reference_distance_m = float(
            reference_route.get("distance", 0) or 0
        )
        reference_duration_s = float(
            reference_route.get("duration", 0) or 0
        )

        if reference_distance_m <= 0 or reference_duration_s <= 0:
            raise OSRMError("OSRM returned an invalid reference route.")
        # ====================================================================
        # 2. AUTOMATIC ROUTE CANDIDATE DISCOVERY
        # ====================================================================

        # OSRM's alternatives=true is not guaranteed to return several
        # genuinely different routes. Therefore we explicitly explore
        # different geographic corridors.
        #
        # This is NOT hardcoded road discovery:
        #
        # origin -> corridor points -> destination
        #
        # OSRM snaps the corridor points to the actual OSM road graph.
        #
        # Each pair creates a different corridor through the trip.
        # Skipped entirely when the caller asked for a single route.
        corridor_pairs = (
            self._build_corridor_waypoints(
                origin_lat=origin_lat,
                origin_lon=origin_lon,
                destination_lat=destination_lat,
                destination_lon=destination_lon,
            )
            if request.alternatives
            else []
        )

        for waypoints in corridor_pairs:
            try:
                candidate_payload = await self._route_with_waypoints(
                    origin_lat=origin_lat,
                    origin_lon=origin_lon,
                    destination_lat=destination_lat,
                    destination_lon=destination_lon,
                    waypoints=waypoints,
                    profile=osrm_profile,
                    overview=request.overview,
                    steps=request.steps,
                )

                candidate_routes = list(
                    candidate_payload.get("routes", []) or []
                )

                if candidate_routes:
                    osrm_routes.extend(candidate_routes)

            except Exception as exc:
                # One failed corridor must never kill the whole routing
                # request. The direct route is still valid.
                logger.debug(
                    "Skipping corridor %s: %s",
                    waypoints,
                    exc,
                )

        # ====================================================================
        # 3. DEDUPLICATE ROUTES
        # ====================================================================

        osrm_routes = self._deduplicate_routes(
            osrm_routes,
            reference_route=reference_route,
            max_routes=8,
        )

        if not osrm_routes:
            raise OSRMError(
                "OSRM returned no usable route candidates."
            )

        logger.info(
            "Generated %d automatic route candidate(s).",
            len(osrm_routes),
        )

        # ====================================================================
        # 4. OPTIONAL TOMTOM LIVE TRAFFIC
        # ====================================================================

        tomtom_data: Optional[Dict[str, Any]] = None

        if vehicle == "car" and self.tomtom_api_key:
            try:
                tomtom_data = await self._get_tomtom_routes(
                    origin_lat=origin_lat,
                    origin_lon=origin_lon,
                    destination_lat=destination_lat,
                    destination_lon=destination_lon,
                )
            except Exception as exc:
                logger.warning(
                    "TomTom live traffic unavailable. "
                    "Continuing with OSRM: %s",
                    exc,
                )
                tomtom_data = None

        # ====================================================================
        # 5. BUILD ROUTE RESULTS
        # ====================================================================

        results: List[RouteResult] = []

        for index, osrm_route in enumerate(osrm_routes):
            distance_m = float(
                osrm_route.get("distance", 0) or 0
            )
            duration_s = float(
                osrm_route.get("duration", 0) or 0
            )

            distance_km = distance_m / 1000.0
            base_eta_min = duration_s / 60.0

            geometry = extract_route_geometry(osrm_route)

            raw_steps = extract_route_steps(osrm_route)

            steps: List[RouteStep] = []

            for step in raw_steps:
                steps.append(
                    RouteStep(
                        name=str(
                            step.get("name", "") or ""
                        ),
                        distance_m=float(
                            step.get("distance_m", 0) or 0
                        ),
                        duration_s=float(
                            step.get("duration_s", 0) or 0
                        ),
                        instruction=step.get("instruction"),
                    )
                )

            # ---------------------------------------------------------------
            # Route summary
            # ---------------------------------------------------------------

            road_names: List[str] = []

            for step in steps:
                name = (step.name or "").strip()

                if name and name not in road_names:
                    road_names.append(name)

            summary = ", ".join(road_names[:5])

            # ---------------------------------------------------------------
            # Traffic defaults
            # ---------------------------------------------------------------

            live_eta_min = base_eta_min
            traffic_delay_min = 0.0
            traffic_ratio = 1.0
            traffic_status = "UNKNOWN"
            traffic_source = "OSRM"
            intelligence_available = False

            # ---------------------------------------------------------------
            # TomTom
            #
            # IMPORTANT:
            # TomTom alternatives cannot safely be matched to our
            # corridor-generated OSRM routes by list index.
            #
            # Therefore TomTom is applied only to the direct reference route.
            # This avoids falsely claiming that TomTom measured a route
            # it did not actually return.
            # ---------------------------------------------------------------

            tomtom_route: Optional[Dict[str, Any]] = None

            if osrm_route is reference_route:
                tomtom_route = self._select_tomtom_route(
                    tomtom_data,
                    0,
                )

            if tomtom_route:
                traffic_values = self._extract_tomtom_traffic(
                    tomtom_route
                )

                if traffic_values:
                    live_eta_min = traffic_values["live_eta_min"]
                    traffic_delay_min = traffic_values[
                        "traffic_delay_min"
                    ]

                    traffic_source = "TomTom"
                    intelligence_available = True

                    if live_eta_min > 0:
                        base_component = max(
                            live_eta_min - traffic_delay_min,
                            0.1,
                        )

                        traffic_ratio = (
                            live_eta_min / base_component
                        )

                    traffic_status = self._traffic_status(
                        traffic_ratio
                    )

            # ---------------------------------------------------------------
            # Route score
            #
            # Lower score = lower estimated travel cost.
            #
            # For routes without a route-specific TomTom measurement,
            # live_eta_min equals the OSRM base ETA.
            # ---------------------------------------------------------------

            route_score = (
                live_eta_min
                + (0.35 * distance_km)
                + (0.25 * traffic_delay_min)
            )

            # ---------------------------------------------------------------
            # Route classification (relative to the direct OSRM route)
            # ---------------------------------------------------------------

            route_type, route_reason = self._classify(
                osrm_route,
                reference_route,
            )

            route_result = RouteResult(
                route_type=route_type,
                route_reason=route_reason,
                route_id=f"osrm-route-{index + 1}",
                distance_m=distance_m,
                duration_s=duration_s,
                distance_km=round(distance_km, 3),
                duration_min=round(base_eta_min, 2),
                geometry=geometry,
                summary=summary,
                steps=steps,
                live_eta_min=round(live_eta_min, 2),
                base_eta_min=round(base_eta_min, 2),
                traffic_delay_min=round(traffic_delay_min, 2),
                traffic_status=traffic_status,
                traffic_ratio=round(traffic_ratio, 3),
                traffic_source=traffic_source,
                route_score=round(route_score, 3),
                recommended=False,
                intelligence_available=intelligence_available,
            )

            results.append(route_result)

        # ====================================================================
        # 6. SORT BY PROJECT ROUTE SCORE
        # ====================================================================

        results.sort(
            key=lambda route: route.route_score
        )

        # Re-number after sorting so IDs reflect the final UI order.
        for index, route in enumerate(results, start=1):
            route.route_id = f"osrm-route-{index}"

        # ====================================================================
        # 7. MARK RECOMMENDED ROUTE
        # ====================================================================

        if results:
            results[0].recommended = True

        # ====================================================================
        # 8. RESPONSE
        # ====================================================================

        source = (
            "osrm+tomtom"
            if any(
                route.intelligence_available
                for route in results
            )
            else "osrm"
        )

        logger.info(
            "Routing complete: %d route(s), source=%s",
            len(results),
            source,
        )

        return RouteResponse(
            source=source,
            vehicle=request.vehicle,
            routes=results,
        )

    # ========================================================================
    # ROUTE CLASSIFICATION
    # ========================================================================

    @staticmethod
    def _classify(
        route: Dict[str, Any],
        reference_route: Dict[str, Any],
    ) -> Tuple[str, str]:
        """
        Classify a route against the ORIGINAL direct OSRM route.

        Product definitions:
            shortcut    = shorter AND faster
            longcut     = longer AND faster
            alternative = different route without either property

        A 5% margin keeps near-identical routes from being labelled.
        """

        if route is reference_route:
            return "regular", "Normal direct OSRM reference route"

        distance_m = float(route.get("distance", 0) or 0)
        duration_s = float(route.get("duration", 0) or 0)
        reference_distance_m = float(reference_route["distance"])
        reference_duration_s = float(reference_route["duration"])

        shorter_than_reference = distance_m < reference_distance_m * 0.95
        longer_than_reference = distance_m > reference_distance_m * 1.05
        faster_than_reference = duration_s < reference_duration_s * 0.95

        shorter_pct = (1 - distance_m / reference_distance_m) * 100
        longer_pct = (distance_m / reference_distance_m - 1) * 100
        faster_pct = (1 - duration_s / reference_duration_s) * 100

        if shorter_than_reference and faster_than_reference:
            return "shortcut", (
                f"{shorter_pct:.0f}% shorter and {faster_pct:.0f}% "
                "faster than the reference route"
            )

        if longer_than_reference and faster_than_reference:
            return "longcut", (
                f"{longer_pct:.0f}% longer but {faster_pct:.0f}% "
                "faster than the reference route"
            )

        if shorter_than_reference:
            return "alternative", (
                f"{shorter_pct:.0f}% shorter, but not sufficiently "
                "faster than the reference"
            )

        if faster_than_reference:
            return "alternative", (
                f"{faster_pct:.0f}% faster, but not sufficiently "
                "shorter than the reference"
            )

        return "alternative", "Different connected road corridor"

    # ========================================================================
    # AUTOMATIC CORRIDOR GENERATION
    # ========================================================================

    @staticmethod
    def _build_corridor_waypoints(
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
    ) -> List[List[Tuple[float, float]]]:
        """
        Build several pairs of intermediate geographic points.

        The points are intentionally generic. They are not Bengaluru-road
        names and do not assume a particular route.

        OSRM receives these points and snaps them to the actual OSM network.
        """

        # Avoid generating strange candidates for a nearly identical
        # origin/destination pair.
        coordinate_span = math.hypot(
            destination_lat - origin_lat,
            destination_lon - origin_lon,
        )

        if coordinate_span < 1e-5:
            return []

        def corridor_point(
            fraction: float,
            offset: float,
        ) -> Tuple[float, float]:
            # Interpolate on the straight geographic line.
            lat = (
                origin_lat
                + (destination_lat - origin_lat) * fraction
            )
            lon = (
                origin_lon
                + (destination_lon - origin_lon) * fraction
            )

            dlat = destination_lat - origin_lat
            dlon = destination_lon - origin_lon

            length = max(
                math.hypot(dlat, dlon),
                1e-9,
            )

            # Perpendicular unit vector.
            perp_lat = -dlon / length
            perp_lon = dlat / length

            return (
                lat + perp_lat * offset,
                lon + perp_lon * offset,
            )

        # Multiple corridor widths increase the chance of finding
        # genuinely different roads in an irregular city network.
        offsets = (
            0.004,
            -0.004,
            0.008,
            -0.008,
            0.012,
            -0.012,
            0.018,
            -0.018,
            0.026,
            -0.026,
        )

        corridors: List[List[Tuple[float, float]]] = []

        for offset in offsets:
            corridors.append(
                [
                    corridor_point(0.30, offset),
                    corridor_point(0.70, offset),
                ]
            )

        return corridors

    async def _route_with_waypoints(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
        waypoints: Sequence[Tuple[float, float]],
        profile: str,
        overview: bool,
        steps: bool,
    ) -> Dict[str, Any]:
        """
        Request an OSRM route through intermediate points.

        This is intentionally implemented here instead of assuming that
        OSRMClient.route() supports a 'waypoints' keyword. That removes the
        TypeError caused by passing an unsupported argument to the existing
        OSRMClient implementation.
        """

        coordinates: List[str] = [
            f"{origin_lon},{origin_lat}"
        ]

        for lat, lon in waypoints:
            coordinates.append(
                f"{lon},{lat}"
            )

        coordinates.append(
            f"{destination_lon},{destination_lat}"
        )

        coordinate_string = ";".join(coordinates)

        url = (
            f"{self.osrm_base_url}"
            f"/route/v1/{profile}/"
            f"{coordinate_string}"
        )

        # Must match OSRMClient.route(): OSRM rejects overview=true, and
        # without geojson the geometry is a polyline string that
        # extract_route_geometry() discards.
        params = {
            "alternatives": "false",
            "overview": "full" if overview else "false",
            "steps": "true" if steps else "false",
            "geometries": "geojson",
            "annotations": "false",
        }

        timeout = httpx.Timeout(
            10.0,
            connect=3.0,
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise OSRMError(
                f"OSRM waypoint request failed: {exc}"
            ) from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise OSRMError(
                f"OSRM waypoint request failed: "
                f"HTTP {response.status_code}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise OSRMError(
                "OSRM waypoint request returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise OSRMError(
                "OSRM waypoint request returned an invalid response."
            )

        if payload.get("code") != "Ok":
            raise OSRMError(
                str(
                    payload.get(
                        "message",
                        "OSRM waypoint routing failed.",
                    )
                )
            )

        return payload

    # ========================================================================
    # ROUTE DEDUPLICATION
    # ========================================================================

    @staticmethod
    def _deduplicate_routes(
        routes: Sequence[Dict[str, Any]],
        reference_route: Dict[str, Any],
        max_routes: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Remove effectively identical routes.

        The reference route is always kept first so it can never be
        dropped as a duplicate or cut by max_routes.

        Distance and duration are useful first-pass fingerprints. The
        geometry is intentionally retained untouched for the frontend.
        """

        unique_routes: List[Dict[str, Any]] = [reference_route]

        for route in routes:
            if not isinstance(route, dict) or route is reference_route:
                continue

            distance = float(
                route.get("distance", 0) or 0
            )
            duration = float(
                route.get("duration", 0) or 0
            )

            if distance <= 0 or duration <= 0:
                continue

            duplicate = False

            for existing in unique_routes:
                existing_distance = float(
                    existing.get("distance", 0) or 0
                )
                existing_duration = float(
                    existing.get("duration", 0) or 0
                )

                # Treat very similar routes as the same UI candidate.
                if (
                    abs(distance - existing_distance) < 150.0
                    and abs(duration - existing_duration) < 30.0
                ):
                    duplicate = True
                    break

            if not duplicate:
                unique_routes.append(route)

        # Reference first, then fastest base OSRM candidates.
        candidates = sorted(
            unique_routes[1:],
            key=lambda route: float(
                route.get("duration", float("inf"))
            ),
        )

        return [reference_route] + candidates[: max_routes - 1]

    # ========================================================================
    # TOMTOM
    # ========================================================================

    async def _get_tomtom_routes(
        self,
        *,
        origin_lat: float,
        origin_lon: float,
        destination_lat: float,
        destination_lon: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Query TomTom traffic-aware routing.

        TomTom is optional. Failure here must never make OSRM routing fail.
        """

        if not self.tomtom_api_key:
            return None

        locations = (
            f"{origin_lat},{origin_lon}:"
            f"{destination_lat},{destination_lon}"
        )

        params = {
            "key": self.tomtom_api_key,
            "traffic": "true",
            "routeType": "fastest",
            "travelMode": "car",
            "maxAlternatives": "2",
            "instructionsType": "text",
            "language": "en-GB",
        }

        url = (
            f"{self.tomtom_base_url}/"
            f"{locations}/json"
        )

        logger.info(
            "Requesting TomTom live traffic..."
        )

        try:
            timeout = httpx.Timeout(
                4.0,
                connect=2.0,
            )

            async with httpx.AsyncClient(
                timeout=timeout
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                )

                response.raise_for_status()

                data = response.json()

            if not isinstance(data, dict):
                return None

            return data

        except (
            httpx.HTTPError,
            ValueError,
        ) as exc:
            logger.warning(
                "TomTom request failed: %s",
                exc,
            )
            return None

    # ========================================================================
    # TOMTOM ROUTE SELECTION
    # ========================================================================

    @staticmethod
    def _select_tomtom_route(
        tomtom_data: Optional[Dict[str, Any]],
        index: int,
    ) -> Optional[Dict[str, Any]]:
        if not tomtom_data:
            return None

        routes = tomtom_data.get(
            "routes",
            [],
        )

        if not isinstance(routes, list):
            return None

        if not routes:
            return None

        if 0 <= index < len(routes):
            route = routes[index]

            if isinstance(route, dict):
                return route

        return None

    # ========================================================================
    # TOMTOM TRAFFIC EXTRACTION
    # ========================================================================

    @staticmethod
    def _extract_tomtom_traffic(
        route: Dict[str, Any],
    ) -> Optional[Dict[str, float]]:
        """
        Extract TomTom travel time and traffic delay.
        """

        summary = route.get(
            "summary",
            {},
        )

        if not isinstance(summary, dict):
            return None

        travel_time = summary.get(
            "travelTimeInSeconds"
        )

        traffic_delay = summary.get(
            "trafficDelayInSeconds",
            0,
        )

        if travel_time is None:
            return None

        try:
            travel_time = float(
                travel_time
            )

            traffic_delay = float(
                traffic_delay or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if travel_time <= 0:
            return None

        return {
            "live_eta_min": (
                travel_time / 60.0
            ),
            "traffic_delay_min": max(
                traffic_delay / 60.0,
                0.0,
            ),
        }

    # ========================================================================
    # TRAFFIC STATUS
    # ========================================================================

    @staticmethod
    def _traffic_status(
        ratio: float,
    ) -> str:
        """
        Convert live/base travel-time ratio into a project visualization
        category. This is not a TomTom classification.
        """

        if ratio < 1.10:
            return "LOW"

        if ratio < 1.30:
            return "MODERATE"

        if ratio < 1.60:
            return "HIGH"

        return "SEVERE"
