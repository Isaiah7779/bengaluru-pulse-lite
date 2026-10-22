"""Regression tests for route generation and strict route classification."""

import asyncio
import unittest

from routing.route_service import RoutingService
from routing.schemas import Coordinate, RouteRequest, VehicleMode


def route(distance: float, duration: float) -> dict:
    return {
        "distance": distance,
        "duration": duration,
        "geometry": {"type": "LineString", "coordinates": [[77.6, 12.9], [77.7, 13.0]]},
        "legs": [],
    }


class FakeOSRM:
    async def route(self, *args, **kwargs):
        return {"routes": [route(10_000, 1_200), route(12_000, 1_050)]}


class RoutingServiceTests(unittest.TestCase):
    def test_strict_shortcut_and_longcut_classification(self):
        reference = route(10_000, 1_200)
        self.assertEqual(RoutingService._classify(route(9_000, 1_100), reference)[0], "shortcut")
        self.assertEqual(RoutingService._classify(route(11_000, 1_100), reference)[0], "longcut")
        self.assertEqual(RoutingService._classify(route(9_000, 1_300), reference)[0], "alternative")

    def test_corridors_are_generated_outside_nested_scope(self):
        corridors = RoutingService._build_corridor_waypoints(12.9716, 77.5946, 12.9352, 77.6245)
        self.assertEqual(len(corridors), 10)
        self.assertTrue(all(len(candidate) == 2 for candidate in corridors))

    def test_route_result_preserves_reference_and_returns_alternatives(self):
        service = RoutingService("http://unused")
        service.osrm = FakeOSRM()

        async def no_extra_candidates(*args, **kwargs):
            return {"routes": []}

        service._route_with_waypoints = no_extra_candidates
        request = RouteRequest(
            origin=Coordinate(lat=12.9716, lon=77.5946),
            destination=Coordinate(lat=12.9352, lon=77.6245),
            vehicle=VehicleMode.CAR,
        )
        response = asyncio.run(service.calculate_route(request))
        self.assertEqual(response.source, "osrm")
        self.assertEqual(len(response.routes), 2)
        self.assertTrue(response.routes[0].recommended)
        self.assertEqual({item.route_type for item in response.routes}, {"regular", "longcut"})


if __name__ == "__main__":
    unittest.main()
