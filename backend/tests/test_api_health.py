"""Smoke tests for the FastAPI application without external providers."""

import unittest

from fastapi.testclient import TestClient

from main import app


class ApiHealthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint_is_available_without_osrm_or_tomtom(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_locations_endpoint_returns_coordinates(self):
        response = self.client.get("/locations")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()["locations"]), 0)

    def test_prediction_uses_the_loaded_model(self):
        response = self.client.post(
            "/predict",
            json={
                "location": "Silk Board",
                "traffic_volume": 250,
                "average_speed": 15,
                "weather": "Sunny",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("predicted_congestion", response.json())


if __name__ == "__main__":
    unittest.main()
