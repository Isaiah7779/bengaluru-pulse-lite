"""Typed runtime configuration loaded from environment variables / .env.

All configuration lives here. Secrets are SecretStr so they never appear in
repr(), logs or error messages.
"""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


def resolve_backend_path(value: str | Path) -> Path:
    """Resolve relative paths against the backend directory."""

    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # -- application ---------------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "Bengaluru Pulse API"
    app_description: str = "Bengaluru navigation and traffic forecasting API"
    app_version: str = "3.0.0"
    log_level: str = "INFO"
    log_json: bool = False

    cors_origins_raw: str = Field(
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080",
        alias="CORS_ORIGINS",
    )

    # -- database ------------------------------------------------------------
    database_url: str = f"sqlite:///{(BASE_DIR / 'runtime' / 'pulse.db').as_posix()}"
    db_auto_create: bool = Field(
        True,
        description="Create tables with metadata.create_all (dev/test). "
        "Production uses Alembic migrations and sets this to false.",
    )

    # -- routing -------------------------------------------------------------
    osrm_url: str = "http://localhost:5000"  # car graph (legacy name kept)
    osrm_foot_url: Optional[str] = None
    osrm_bicycle_url: Optional[str] = None
    osrm_timeout_seconds: float = 10.0
    max_route_candidates: int = 5

    # -- providers -------------------------------------------------------------
    tomtom_api_key: Optional[SecretStr] = None
    tomtom_daily_budget: int = Field(
        2000, description="Hard cap on TomTom non-tile calls per UTC day (free tier is 2,500)."
    )
    tomtom_timeout_seconds: float = 6.0
    tomtom_route_eval_max: int = Field(
        5, description="Max route candidates evaluated with TomTom per route request."
    )
    openmeteo_url: str = "https://api.open-meteo.com/v1/forecast"
    photon_url: Optional[str] = "https://photon.komoot.io"
    geocode_fallback_enabled: bool = True

    # -- collector -------------------------------------------------------------
    collector_enabled: bool = False
    collector_flow_interval_minutes: int = 30
    collector_weather_interval_minutes: int = 30
    collector_incident_interval_minutes: int = 60
    observation_stale_minutes: int = 90

    # -- retention / privacy -------------------------------------------------
    retention_observation_days: int = 730
    retention_trip_days: int = 180
    retention_submission_trace_days: int = 90

    # -- auth ----------------------------------------------------------------
    jwt_secret: Optional[SecretStr] = None
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    # Firebase Authentication. Only the project ID is needed to verify ID tokens
    # (Google's public signing keys); no service-account key is required.
    firebase_project_id: Optional[str] = None
    # Require a signed-in, verified user for application endpoints (health stays public).
    api_auth_required: bool = True
    # Built-in e-mail/password accounts (pre-Firebase). Kept during the transition;
    # set LEGACY_AUTH_ENABLED=false once every account signs in through Firebase.
    legacy_auth_enabled: bool = True
    legacy_registration_enabled: bool = True

    # -- legacy ML artifacts -------------------------------------------------
    traffic_model_path: str = "traffic_model_tuned.pkl"
    area_encoder_path_raw: str = Field("area_encoder.pkl", alias="AREA_ENCODER_PATH")
    road_encoder_path_raw: str = Field("road_encoder.pkl", alias="ROAD_ENCODER_PATH")
    weather_encoder_path_raw: str = Field("weather_encoder.pkl", alias="WEATHER_ENCODER_PATH")
    traffic_dataset_path: str = "Banglore_traffic_Dataset.csv"
    model_registry_dir: str = "models"

    # ------------------------------------------------------------------------
    @field_validator("firebase_project_id", mode="before")
    @classmethod
    def _empty_is_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("tomtom_api_key", "jwt_secret", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value

    @model_validator(mode="after")
    def _production_requirements(self) -> "Settings":
        if self.environment == "production":
            if self.jwt_secret is None or len(self.jwt_secret.get_secret_value()) < 32:
                raise ValueError("JWT_SECRET (>=32 chars) is required in production")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origin is not allowed in production")
            if os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
                raise ValueError("FIREBASE_AUTH_EMULATOR_HOST must not be set in production")
        return self

    # ------------------------------------------------------------------------
    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def tomtom_key(self) -> Optional[str]:
        return self.tomtom_api_key.get_secret_value() if self.tomtom_api_key else None

    def osrm_url_for(self, profile: str) -> Optional[str]:
        """Base URL of the OSRM server built for an OSRM profile, if configured."""

        return {
            "driving": self.osrm_url,
            "foot": self.osrm_foot_url,
            "cycling": self.osrm_bicycle_url,
        }.get(profile)

    # legacy attribute names used by services.ModelBundle / IncidentService
    @property
    def model_path(self) -> Path:
        return resolve_backend_path(self.traffic_model_path)

    @property
    def area_encoder_path(self) -> Path:
        return resolve_backend_path(self.area_encoder_path_raw)

    @property
    def road_encoder_path(self) -> Path:
        return resolve_backend_path(self.road_encoder_path_raw)

    @property
    def weather_encoder_path(self) -> Path:
        return resolve_backend_path(self.weather_encoder_path_raw)

    @property
    def dataset_path(self) -> Path:
        return resolve_backend_path(self.traffic_dataset_path)

    @property
    def registry_path(self) -> Path:
        return resolve_backend_path(self.model_registry_dir)


_EPHEMERAL_JWT_SECRET = secrets.token_urlsafe(48)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.jwt_secret is None:
        # Development convenience only: tokens die on restart. Production refuses
        # to start without JWT_SECRET (see validator above).
        logger.warning("JWT_SECRET not set; using an ephemeral development secret")
        settings.jwt_secret = SecretStr(_EPHEMERAL_JWT_SECRET)
    return settings
