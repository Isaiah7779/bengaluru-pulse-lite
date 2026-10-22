"""TomTom traffic provider: flow segments, incidents, traffic-aware route timing.

Error messages never include request URLs (they contain the API key).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from core.http import async_client

from core.settings import Settings
from providers.quota import QuotaExceeded, QuotaGuard

logger = logging.getLogger(__name__)

BASE = "https://api.tomtom.com"
# Bengaluru Metropolitan Region incl. Kempegowda Intl Airport (minLon,minLat,maxLon,maxLat), ~3,000 km².
BENGALURU_BBOX = (77.35, 12.75, 77.90, 13.26)


class ProviderError(Exception):
    """Safe-to-display provider failure (no secrets)."""


class ProviderUnavailable(ProviderError):
    """Provider not configured or quota exhausted."""


@dataclass
class FlowReading:
    current_speed_kmph: float
    free_flow_speed_kmph: float
    current_travel_time_s: Optional[float]
    free_flow_travel_time_s: Optional[float]
    confidence: Optional[float]
    road_closure: bool
    road_class: Optional[str]
    geometry: Optional[List[List[float]]]  # [[lon, lat], ...]
    fetched_at: datetime

    @property
    def speed_ratio(self) -> float:
        return self.current_speed_kmph / self.free_flow_speed_kmph


@dataclass
class IncidentReading:
    external_id: str
    category: str
    severity: Optional[int]
    description: Optional[str]
    road_from: Optional[str]
    road_to: Optional[str]
    lat: float
    lon: float
    geometry: Optional[Dict[str, Any]]
    delay_s: Optional[float]
    start_time: Optional[datetime]
    end_time: Optional[datetime]


@dataclass
class RouteTiming:
    """TomTom's timing for a route geometry we supplied."""

    length_m: float
    travel_time_s: float
    traffic_delay_s: float
    no_traffic_s: Optional[float]
    historic_s: Optional[float]
    live_s: Optional[float]
    departure: Optional[datetime]
    arrival: Optional[datetime]
    raw_summary: Dict[str, Any] = field(default_factory=dict)


ICON_CATEGORIES = {
    0: "unknown", 1: "accident", 2: "fog", 3: "dangerous_conditions", 4: "rain", 5: "ice",
    6: "jam", 7: "lane_closed", 8: "road_closed", 9: "road_works", 10: "wind",
    11: "flooding", 14: "broken_down_vehicle",
}


def _parse_time(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_flow(payload: Dict[str, Any], fetched_at: Optional[datetime] = None) -> FlowReading:
    """Validate a flowSegmentData payload. Raises ProviderError on invalid data."""

    flow = payload.get("flowSegmentData") if isinstance(payload, dict) else None
    if not isinstance(flow, dict):
        raise ProviderError("TomTom flow response missing flowSegmentData")
    try:
        current = float(flow["currentSpeed"])
        free = float(flow["freeFlowSpeed"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderError("TomTom flow response missing speeds") from exc
    closure = bool(flow.get("roadClosure", False))
    if not (0 < free <= 200) or not (0 <= current <= 200) or (current == 0 and not closure):
        raise ProviderError(f"TomTom flow speeds out of range (current={current}, free={free})")
    confidence = flow.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else None
    if confidence is not None and not 0 <= confidence <= 1:
        confidence = None
    coords = (flow.get("coordinates") or {}).get("coordinate") or []
    geometry = [
        [float(c["longitude"]), float(c["latitude"])]
        for c in coords
        if isinstance(c, dict) and "latitude" in c and "longitude" in c
    ] or None

    def opt(key: str) -> Optional[float]:
        value = flow.get(key)
        return float(value) if isinstance(value, (int, float)) and value >= 0 else None

    return FlowReading(
        current_speed_kmph=current,
        free_flow_speed_kmph=free,
        current_travel_time_s=opt("currentTravelTime"),
        free_flow_travel_time_s=opt("freeFlowTravelTime"),
        confidence=confidence,
        road_closure=closure,
        road_class=flow.get("frc"),
        geometry=geometry,
        fetched_at=fetched_at or datetime.now(timezone.utc),
    )


def parse_incidents(payload: Dict[str, Any]) -> List[IncidentReading]:
    readings: List[IncidentReading] = []
    for item in (payload or {}).get("incidents", []) or []:
        props = item.get("properties") or {}
        geometry = item.get("geometry") or {}
        coords = geometry.get("coordinates")
        point: Optional[Tuple[float, float]] = None
        try:
            if geometry.get("type") == "Point":
                point = (float(coords[1]), float(coords[0]))
            elif geometry.get("type") == "LineString" and coords:
                mid = coords[len(coords) // 2]
                point = (float(mid[1]), float(mid[0]))
        except (TypeError, ValueError, IndexError):
            point = None
        external_id = props.get("id")
        if not external_id or point is None:
            continue  # unusable record
        events = props.get("events") or []
        description = "; ".join(e.get("description", "") for e in events if e.get("description")) or None
        delay = props.get("delay")
        readings.append(
            IncidentReading(
                external_id=str(external_id),
                category=ICON_CATEGORIES.get(props.get("iconCategory"), "other"),
                severity=props.get("magnitudeOfDelay") if isinstance(props.get("magnitudeOfDelay"), int) else None,
                description=description,
                road_from=props.get("from"),
                road_to=props.get("to"),
                lat=point[0],
                lon=point[1],
                geometry=geometry if geometry.get("type") else None,
                delay_s=float(delay) if isinstance(delay, (int, float)) else None,
                start_time=_parse_time(props.get("startTime")),
                end_time=_parse_time(props.get("endTime")),
            )
        )
    return readings


def downsample(points: Sequence[Sequence[float]], max_points: int) -> List[Sequence[float]]:
    """Keep first/last and evenly spaced interior points."""

    if len(points) <= max_points:
        return list(points)
    step = (len(points) - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]


class TomTomProvider:
    name = "tomtom"

    def __init__(self, settings: Settings, quota: Optional[QuotaGuard] = None) -> None:
        self.key = settings.tomtom_key
        self.timeout = settings.tomtom_timeout_seconds
        self.quota = quota or QuotaGuard("tomtom", settings.tomtom_daily_budget)

    @property
    def configured(self) -> bool:
        return bool(self.key)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        endpoint: str,
        purpose: str,
        background: bool,
        params: Dict[str, Any],
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.key:
            raise ProviderUnavailable("TomTom API key not configured")
        try:
            call_id = self.quota.acquire(endpoint, purpose, background=background)
        except QuotaExceeded as exc:
            raise ProviderUnavailable(str(exc)) from exc
        status: Optional[int] = None
        try:
            async with async_client(self.timeout) as client:
                response = await client.request(
                    method, BASE + path, params={**params, "key": self.key}, json=json_body
                )
            status = response.status_code
            if status == 403:
                raise ProviderUnavailable("TomTom rejected the request (quota or key)")
            if status >= 400:
                raise ProviderError(f"TomTom {endpoint} returned HTTP {status}")
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderError(f"TomTom {endpoint} returned non-object JSON")
            self.quota.finish(call_id, status, True)
            return data
        except httpx.TimeoutException as exc:
            self.quota.finish(call_id, status, False, "timeout")
            raise ProviderError(f"TomTom {endpoint} timed out") from None
        except httpx.HTTPError as exc:
            self.quota.finish(call_id, status, False, type(exc).__name__)
            raise ProviderError(f"TomTom {endpoint} network error ({type(exc).__name__})") from None
        except ValueError:
            self.quota.finish(call_id, status, False, "invalid json")
            raise ProviderError(f"TomTom {endpoint} returned invalid JSON") from None
        except ProviderError as exc:
            self.quota.finish(call_id, status, False, str(exc))
            raise

    async def flow_segment(self, lat: float, lon: float, *, purpose: str = "interactive", background: bool = False) -> FlowReading:
        data = await self._request(
            "GET",
            "/traffic/services/4/flowSegmentData/absolute/10/json",
            endpoint="flow",
            purpose=purpose,
            background=background,
            params={"point": f"{lat},{lon}", "unit": "KMPH"},
        )
        return parse_flow(data)

    async def incidents(self, bbox: Tuple[float, float, float, float] = BENGALURU_BBOX, *, background: bool = True) -> List[IncidentReading]:
        fields = (
            "{incidents{type,geometry{type,coordinates},properties{id,iconCategory,magnitudeOfDelay,"
            "events{description,code},startTime,endTime,from,to,length,delay}}}"
        )
        data = await self._request(
            "GET",
            "/traffic/services/5/incidentDetails",
            endpoint="incidents",
            purpose="collector" if background else "interactive",
            background=background,
            params={
                "bbox": ",".join(str(v) for v in bbox),
                "fields": fields,
                "language": "en-GB",
                "timeValidityFilter": "present",
            },
        )
        return parse_incidents(data)

    async def route_timing(
        self,
        coordinates: Sequence[Sequence[float]],
        *,
        depart_at: Optional[datetime] = None,
        travel_mode: str = "car",
        purpose: str = "route_eval",
    ) -> RouteTiming:
        """Time a given route geometry ([[lon, lat], ...]) with TomTom traffic.

        The geometry is passed as supportingPoints so TomTom reconstructs (rather
        than replaces) our OSRM route. Callers must check `length_m` against the
        OSRM distance to confirm the reconstruction matched.
        """

        if len(coordinates) < 2:
            raise ProviderError("Route geometry too short")
        points = downsample(coordinates, 120)
        origin, destination = points[0], points[-1]
        locations = f"{origin[1]},{origin[0]}:{destination[1]},{destination[0]}"
        params: Dict[str, Any] = {
            "traffic": "true",
            "travelMode": travel_mode,
            "routeType": "fastest",
            "computeTravelTimeFor": "all",
            "routeRepresentation": "summaryOnly",
        }
        if depart_at is not None:
            params["departAt"] = depart_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = {"supportingPoints": [{"latitude": p[1], "longitude": p[0]} for p in points]}
        data = await self._request(
            "POST",
            f"/routing/1/calculateRoute/{locations}/json",
            endpoint="routing",
            purpose=purpose,
            background=False,
            params=params,
            json_body=body,
        )
        routes = data.get("routes") or []
        if not routes or not isinstance(routes[0], dict):
            raise ProviderError("TomTom routing returned no route")
        summary = routes[0].get("summary") or {}
        try:
            travel = float(summary["travelTimeInSeconds"])
            length = float(summary["lengthInMeters"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("TomTom routing summary incomplete") from exc
        if travel <= 0 or length <= 0 or math.isnan(travel):
            raise ProviderError("TomTom routing summary invalid")

        def opt(key: str) -> Optional[float]:
            value = summary.get(key)
            return float(value) if isinstance(value, (int, float)) else None

        return RouteTiming(
            length_m=length,
            travel_time_s=travel,
            traffic_delay_s=max(opt("trafficDelayInSeconds") or 0.0, 0.0),
            no_traffic_s=opt("noTrafficTravelTimeInSeconds"),
            historic_s=opt("historicTrafficTravelTimeInSeconds"),
            live_s=opt("liveTrafficIncidentsTravelTimeInSeconds"),
            departure=_parse_time(summary.get("departureTime")),
            arrival=_parse_time(summary.get("arrivalTime")),
            raw_summary={k: v for k, v in summary.items() if not isinstance(v, (dict, list))},
        )
