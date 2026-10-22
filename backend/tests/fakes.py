"""Deterministic fakes for OSRM and TomTom (labelled test fixtures, not data)."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from providers.tomtom import ProviderError, RouteTiming
from routing.geometry import line_length_m
from routing.osrm_client import OSRMError


def straight(a, b, n=40) -> List[List[float]]:
    """Line from (lat, lon) a to b as [lon, lat] coordinates."""

    return [[a[1] + (b[1] - a[1]) * i / (n - 1), a[0] + (b[0] - a[0]) * i / (n - 1)] for i in range(n)]


def via(a, m, b, n=40) -> List[List[float]]:
    return straight(a, m, n)[:-1] + straight(m, b, n)


def osrm_route(coords, speed_mps=10.0, duration=None):
    distance = line_length_m(coords)
    return {
        "distance": distance,
        "duration": duration if duration is not None else distance / speed_mps,
        "geometry": {"type": "LineString", "coordinates": coords},
        "legs": [
            {
                "steps": [
                    {"name": "Test Road", "distance": distance, "duration": distance / speed_mps,
                     "maneuver": {"type": "depart", "bearing_after": 90, "location": coords[0]}},
                    {"name": "", "distance": 0, "duration": 0, "maneuver": {"type": "arrive", "location": coords[-1]}},
                ]
            }
        ],
    }


class FakeOSRM:
    """Returns a scripted primary response and scripted corridor routes."""

    def __init__(self, primary_routes: Sequence[dict], corridor_routes: Sequence[Optional[dict]] = (), fail: bool = False):
        self.primary_routes = list(primary_routes)
        self.corridor_routes = list(corridor_routes)
        self.fail = fail
        self.calls: List[dict] = []
        self._corridor_index = 0

    async def route_points(self, points, *, profile="driving", alternatives=0, steps=True, exclude=()):
        self.calls.append({"points": list(points), "profile": profile, "exclude": list(exclude)})
        if self.fail:
            raise OSRMError("Routing engine unreachable (ConnectError)")
        if len(points) == 2:
            return {"code": "Ok", "routes": self.primary_routes, "waypoints": [{"distance": 3.0}, {"distance": 4.0}]}
        if self._corridor_index < len(self.corridor_routes):
            route = self.corridor_routes[self._corridor_index]
            self._corridor_index += 1
            if route is None:
                raise OSRMError("no route")
            return {"code": "Ok", "routes": [route]}
        raise OSRMError("no route")

    async def health(self):
        return not self.fail


class FakeTomTom:
    """Times a route as base distance / speed plus a scripted delay."""

    configured = True

    def __init__(self, delay_by_length: Optional[Dict[int, float]] = None, length_factor: float = 1.0,
                 speed_mps: float = 6.0, fail: Optional[Exception] = None):
        self.delay_by_length = delay_by_length or {}
        self.length_factor = length_factor
        self.speed_mps = speed_mps
        self.fail = fail
        self.calls = 0

    async def route_timing(self, coordinates, *, depart_at=None, travel_mode="car", purpose="route_eval"):
        self.calls += 1
        if self.fail:
            raise self.fail
        length = line_length_m(coordinates)
        delay = self.delay_by_length.get(round(length / 1000), 60.0)
        base = length / self.speed_mps
        return RouteTiming(
            length_m=length * self.length_factor, travel_time_s=base + delay, traffic_delay_s=delay,
            no_traffic_s=base, historic_s=None, live_s=base + delay, departure=depart_at, arrival=None,
        )


class NullWeather:
    async def at(self, lat, lon, when):
        return None

    async def current(self, lat, lon):
        return None


__all__ = ["FakeOSRM", "FakeTomTom", "NullWeather", "osrm_route", "straight", "via", "ProviderError"]
