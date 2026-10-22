"""ORM models for Bengaluru Pulse.

Spatial strategy: every located entity stores `lat`/`lon` (portable, indexed).
On PostgreSQL the Alembic migration additionally adds a generated
`geog geography(Point,4326)` column plus a GiST index for spatial queries; SQLite
(tests) works without PostGIS.

All timestamps are timezone-aware UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise DB datetimes (SQLite returns naive values) to aware UTC."""

    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Users and auth
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(16), default="user", index=True)  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[Optional[str]] = mapped_column(String(128))
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Personal data (owned by a user; deletable by the user)
# ---------------------------------------------------------------------------


class FavouritePlace(Base):
    __tablename__ = "favourite_places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(80))
    name: Mapped[Optional[str]] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Trip(Base):
    """A route search the user chose to keep in their history."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    origin_label: Mapped[Optional[str]] = mapped_column(String(200))
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    destination_label: Mapped[Optional[str]] = mapped_column(String(200))
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lon: Mapped[float] = mapped_column(Float)
    vehicle: Mapped[str] = mapped_column(String(16))
    preference: Mapped[str] = mapped_column(String(32))
    depart_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    chosen_route: Mapped[Optional[dict]] = mapped_column(JSON)  # metrics summary, no raw GPS
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Traffic, weather, incidents (observations)
# ---------------------------------------------------------------------------


class TrafficSegment(Base):
    """A monitored road location polled from a traffic provider."""

    __tablename__ = "traffic_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    road_class: Mapped[Optional[str]] = mapped_column(String(16))  # TomTom FRC
    geometry: Mapped[Optional[dict]] = mapped_column(JSON)  # last provider polyline
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    observations = relationship("TrafficObservation", back_populates="segment", passive_deletes=True)


class TrafficObservation(Base):
    __tablename__ = "traffic_observations"
    __table_args__ = (
        UniqueConstraint("segment_id", "observed_at", "source", name="uq_traffic_obs_segment_time"),
        Index("ix_traffic_obs_segment_time", "segment_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_id: Mapped[int] = mapped_column(ForeignKey("traffic_segments.id", ondelete="CASCADE"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)  # minute bucket
    source: Mapped[str] = mapped_column(String(32))
    current_speed_kmph: Mapped[float] = mapped_column(Float)
    free_flow_speed_kmph: Mapped[float] = mapped_column(Float)
    current_travel_time_s: Mapped[Optional[float]] = mapped_column(Float)
    free_flow_travel_time_s: Mapped[Optional[float]] = mapped_column(Float)
    speed_ratio: Mapped[float] = mapped_column(Float)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    road_closure: Mapped[bool] = mapped_column(Boolean, default=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    segment = relationship("TrafficSegment", back_populates="observations")


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (UniqueConstraint("area", "observed_at", "source", name="uq_weather_area_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area: Mapped[str] = mapped_column(String(64), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32))
    temperature_c: Mapped[Optional[float]] = mapped_column(Float)
    precipitation_mm: Mapped[Optional[float]] = mapped_column(Float)
    rain_mm: Mapped[Optional[float]] = mapped_column(Float)
    weather_code: Mapped[Optional[int]] = mapped_column(Integer)
    wind_speed_kmh: Mapped[Optional[float]] = mapped_column(Float)
    visibility_m: Mapped[Optional[float]] = mapped_column(Float)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_incident_source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # tomtom | community
    external_id: Mapped[str] = mapped_column(String(128))
    category: Mapped[str] = mapped_column(String(48))
    severity: Mapped[Optional[int]] = mapped_column(Integer)  # 0..4 (TomTom magnitudeOfDelay)
    description: Mapped[Optional[str]] = mapped_column(Text)
    road_from: Mapped[Optional[str]] = mapped_column(String(200))
    road_to: Mapped[Optional[str]] = mapped_column(String(200))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    geometry: Mapped[Optional[dict]] = mapped_column(JSON)
    delay_s: Mapped[Optional[float]] = mapped_column(Float)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reported_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="published")  # community: pending/published/rejected


class ProviderCall(Base):
    """Every outbound call to a quota-limited provider (budget + freshness)."""

    __tablename__ = "provider_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    endpoint: Mapped[str] = mapped_column(String(48))
    purpose: Mapped[str] = mapped_column(String(32))
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(String(200))


# ---------------------------------------------------------------------------
# Geocoding gazetteer (from OpenStreetMap)
# ---------------------------------------------------------------------------


class Place(Base):
    __tablename__ = "places"
    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_place_osm"),
        Index("ix_places_latlon", "lat", "lon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    osm_type: Mapped[str] = mapped_column(String(1))  # n / w / r
    osm_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(200))
    name_normalized: Mapped[str] = mapped_column(String(200), index=True)
    alt_names: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(48))
    locality: Mapped[Optional[str]] = mapped_column(String(120))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    importance: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------------------
# Community intelligence
# ---------------------------------------------------------------------------


class ShortcutCandidate(Base):
    __tablename__ = "shortcut_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signature: Mapped[str] = mapped_column(String(64), index=True)  # dedup key
    vehicle: Mapped[str] = mapped_column(String(16))
    origin_lat: Mapped[float] = mapped_column(Float)
    origin_lon: Mapped[float] = mapped_column(Float)
    destination_lat: Mapped[float] = mapped_column(Float)
    destination_lon: Mapped[float] = mapped_column(Float)
    geometry: Mapped[dict] = mapped_column(JSON)
    distance_m: Mapped[float] = mapped_column(Float)
    median_duration_s: Mapped[Optional[float]] = mapped_column(Float)
    reference_distance_m: Mapped[Optional[float]] = mapped_column(Float)
    reference_duration_s: Mapped[Optional[float]] = mapped_column(Float)
    classification: Mapped[str] = mapped_column(String(16))  # shortcut | longcut | alternative
    state: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    checks: Mapped[Optional[dict]] = mapped_column(JSON)
    review_note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    submissions = relationship("RouteSubmission", back_populates="candidate")


class RouteSubmission(Base):
    __tablename__ = "route_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vehicle: Mapped[str] = mapped_column(String(16))
    trace: Mapped[Optional[list]] = mapped_column(JSON)  # raw points; purged after retention period
    note: Mapped[Optional[str]] = mapped_column(String(500))
    matched_geometry: Mapped[Optional[dict]] = mapped_column(JSON)
    matched_distance_m: Mapped[Optional[float]] = mapped_column(Float)
    observed_duration_s: Mapped[Optional[float]] = mapped_column(Float)
    match_confidence: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|accepted|rejected
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(300))
    checks: Mapped[Optional[dict]] = mapped_column(JSON)
    candidate_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shortcut_candidates.id", ondelete="SET NULL"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    candidate = relationship("ShortcutCandidate", back_populates="submissions")


# ---------------------------------------------------------------------------
# ML registry
# ---------------------------------------------------------------------------


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_model_name_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    task: Mapped[str] = mapped_column(String(64))
    algorithm: Mapped[str] = mapped_column(String(64))
    dataset: Mapped[str] = mapped_column(String(128))
    dataset_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dataset_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    splits: Mapped[Optional[dict]] = mapped_column(JSON)
    params: Mapped[Optional[dict]] = mapped_column(JSON)
    features: Mapped[Optional[list]] = mapped_column(JSON)
    artifact_path: Mapped[Optional[str]] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="candidate")  # candidate|active|retired
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvaluationRecord(Base):
    __tablename__ = "evaluation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"), index=True)
    split: Mapped[str] = mapped_column(String(16))  # validation | test | online
    horizon: Mapped[str] = mapped_column(String(16))
    candidate: Mapped[Optional[str]] = mapped_column(String(64))  # e.g. baseline:persistence, model:hgb_lr0.05_l15
    metric: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Float)
    n_samples: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PredictionRecord(Base):
    __tablename__ = "prediction_records"
    __table_args__ = (Index("ix_pred_segment_target", "segment_id", "target_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id", ondelete="CASCADE"))
    segment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("traffic_segments.id", ondelete="CASCADE"))
    made_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    target_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_minutes: Mapped[int] = mapped_column(Integer)
    predicted_value: Mapped[float] = mapped_column(Float)
    actual_value: Mapped[Optional[float]] = mapped_column(Float)


# ---------------------------------------------------------------------------
# Legacy prediction history (previously SQLite `predictions`)
# ---------------------------------------------------------------------------


class LegacyPrediction(Base):
    __tablename__ = "legacy_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    location: Mapped[str] = mapped_column(String(64))
    traffic_volume: Mapped[int] = mapped_column(Integer)
    average_speed: Mapped[float] = mapped_column(Float)
    weather: Mapped[str] = mapped_column(String(32))
    predicted_congestion: Mapped[float] = mapped_column(Float)
    traffic_status: Mapped[str] = mapped_column(String(16))
