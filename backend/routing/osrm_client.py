"""Async OSRM HTTP client (route, match, nearest, health).

Coordinates are taken as (lat, lon) tuples by callers and converted to OSRM's
lon,lat order here.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from core.http import async_client

logger = logging.getLogger(__name__)

LatLon = Tuple[float, float]


class OSRMError(Exception):
    """OSRM failed or returned no usable route (message is safe to display)."""


class OSRMNoRoute(OSRMError):
    """OSRM is up but found no route (e.g. point not connected to the network)."""


class OSRMClient:
    def __init__(self, base_url: str = "http://localhost:5000", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with async_client(httpx.Timeout(self.timeout, connect=3.0)) as client:
                response = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise OSRMError("Routing engine timed out") from exc
        except httpx.HTTPError as exc:
            raise OSRMError(f"Routing engine unreachable ({type(exc).__name__})") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise OSRMError(f"Routing engine returned invalid response (HTTP {response.status_code})") from exc
        code = payload.get("code") if isinstance(payload, dict) else None
        if code in {"NoRoute", "NoSegment", "NoMatch"}:
            raise OSRMNoRoute(payload.get("message") or code)
        if response.status_code >= 400 or code != "Ok":
            message = payload.get("message") if isinstance(payload, dict) else None
            raise OSRMError(f"Routing engine error: {message or code or response.status_code}")
        return payload

    @staticmethod
    def _coords(points: Sequence[LatLon]) -> str:
        return ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)

    async def route_points(
        self,
        points: Sequence[LatLon],
        *,
        profile: str = "driving",
        alternatives: int = 0,
        steps: bool = True,
        exclude: Sequence[str] = (),
    ) -> Dict[str, Any]:
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true" if steps else "false",
            "alternatives": str(alternatives) if alternatives else "false",
        }
        if exclude:
            params["exclude"] = ",".join(exclude)
        payload = await self._get(f"/route/v1/{profile}/{self._coords(points)}", params)
        if not payload.get("routes"):
            raise OSRMNoRoute("No route found")
        return payload

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
        """Backward-compatible two-point route."""

        return await self.route_points(
            [(origin_lat, origin_lon), (destination_lat, destination_lon)],
            profile=profile,
            alternatives=3 if alternatives else 0,
            steps=steps,
        )

    async def match(
        self,
        points: Sequence[LatLon],
        timestamps: Optional[Sequence[int]] = None,
        radiuses: Optional[Sequence[float]] = None,
        profile: str = "driving",
    ) -> Dict[str, Any]:
        params = {"overview": "full", "geometries": "geojson", "tidy": "true", "gaps": "split"}
        if timestamps:
            params["timestamps"] = ";".join(str(int(t)) for t in timestamps)
        if radiuses:
            params["radiuses"] = ";".join(f"{r:.0f}" for r in radiuses)
        return await self._get(f"/match/v1/{profile}/{self._coords(points)}", params)

    async def nearest(self, lat: float, lon: float, profile: str = "driving") -> Dict[str, Any]:
        return await self._get(f"/nearest/v1/{profile}/{lon:.6f},{lat:.6f}", {"number": "1"})

    async def health(self) -> bool:
        try:
            await self.nearest(12.9716, 77.5946)
            return True
        except Exception:
            return False


def extract_route_geometry(route: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    geometry = route.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type") and geometry.get("coordinates"):
        return geometry
    return None


def extract_route_steps(route: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalised turn-by-turn steps with human-readable instructions."""

    result: List[Dict[str, Any]] = []
    for leg in route.get("legs") or []:
        for step in (leg or {}).get("steps") or []:
            maneuver = step.get("maneuver") or {}
            name = step.get("name") or step.get("ref") or ""
            result.append(
                {
                    "name": name,
                    "distance_m": float(step.get("distance") or 0),
                    "duration_s": float(step.get("duration") or 0),
                    "instruction": describe_maneuver(maneuver, name, step.get("rotary_name")),
                    "maneuver_type": maneuver.get("type"),
                    "modifier": maneuver.get("modifier"),
                    "location": maneuver.get("location"),
                }
            )
    return result


def describe_maneuver(maneuver: Dict[str, Any], road: str, rotary: Optional[str] = None) -> str:
    kind = maneuver.get("type") or "continue"
    modifier = (maneuver.get("modifier") or "").replace("_", " ")
    onto = f" onto {road}" if road else ""
    if kind == "depart":
        return f"Head {_bearing(maneuver.get('bearing_after'))}{onto}".strip()
    if kind == "arrive":
        return "Arrive at destination" + (f" ({modifier})" if modifier and modifier != "straight" else "")
    if kind in {"roundabout", "rotary", "roundabout turn"}:
        exit_no = maneuver.get("exit")
        name = f" {rotary}" if rotary else ""
        return f"At the roundabout{name}, take exit {exit_no}{onto}" if exit_no else f"Enter the roundabout{onto}"
    if kind in {"merge", "on ramp", "off ramp", "fork"}:
        return f"{kind.capitalize()} {modifier}{onto}".replace("  ", " ").strip()
    if kind == "end of road":
        return f"At the end of the road turn {modifier}{onto}".strip()
    if kind == "new name":
        return f"Continue{onto}" if road else "Continue"
    if modifier in {"uturn"}:
        return f"Make a U-turn{onto}"
    if modifier:
        verb = "Continue" if modifier == "straight" else f"Turn {modifier}"
        return f"{verb}{onto}"
    return f"Continue{onto}"


def _bearing(deg: Any) -> str:
    if not isinstance(deg, (int, float)):
        return ""
    names = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]
    return names[int((deg % 360) / 45 + 0.5) % 8]
