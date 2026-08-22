"""Application configuration for Bengaluru Pulse."""

from functools import lru_cache
import os
from pathlib import Path
from typing import List


BASE_DIR = Path(__file__).resolve().parent


def resolve_backend_path(value: str) -> Path:
    """Resolve relative config paths against the backend directory."""

    path = Path(value)

    if path.is_absolute():
        return path

    return BASE_DIR / path


class Settings:
    """Runtime settings loaded from environment variables."""

    app_name: str = "Bengaluru Pulse API"
    app_description: str = (
        "AI-Powered Urban Traffic Intelligence System"
    )
    app_version: str = "2.2.0"

    cors_origins: List[str]

    model_path: Path
    area_encoder_path: Path
    road_encoder_path: Path
    weather_encoder_path: Path

    dataset_path: Path

    astram_url: str
    astram_timeout_seconds: float

    def __init__(self) -> None:

        # ------------------------------------------------------
        # CORS
        # ------------------------------------------------------

        raw_origins = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        )

        self.cors_origins = [
            origin.strip()
            for origin in raw_origins.split(",")
            if origin.strip()
        ]

        # ------------------------------------------------------
        # ML MODEL
        # ------------------------------------------------------

        self.model_path = resolve_backend_path(
            os.getenv(
                "TRAFFIC_MODEL_PATH",
                "traffic_model_tuned.pkl",
            )
        )

        # ------------------------------------------------------
        # ENCODERS
        # ------------------------------------------------------

        self.area_encoder_path = resolve_backend_path(
            os.getenv(
                "AREA_ENCODER_PATH",
                "area_encoder.pkl",
            )
        )

        self.road_encoder_path = resolve_backend_path(
            os.getenv(
                "ROAD_ENCODER_PATH",
                "road_encoder.pkl",
            )
        )

        self.weather_encoder_path = resolve_backend_path(
            os.getenv(
                "WEATHER_ENCODER_PATH",
                "weather_encoder.pkl",
            )
        )

        # ------------------------------------------------------
        # DATASET
        # ------------------------------------------------------

        self.dataset_path = resolve_backend_path(
            os.getenv(
                "TRAFFIC_DATASET_PATH",
                "traffic_dataset.csv",
            )
        )

        # ------------------------------------------------------
        # INCIDENT API
        # ------------------------------------------------------

        self.astram_url = os.getenv(
            "ASTRAM_INCIDENTS_URL",
            "https://karnataka.gov.in",
        )

        self.astram_timeout_seconds = float(
            os.getenv(
                "ASTRAM_TIMEOUT_SECONDS",
                "10",
            )
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()