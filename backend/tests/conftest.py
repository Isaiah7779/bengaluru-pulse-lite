"""Test configuration.

Unit tests run fully offline: SQLite, fake OSRM/TomTom, no real API key.
Tests marked `integration` talk to live local services (OSRM, PostGIS) and are
skipped automatically when those are unreachable.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_TMP = tempfile.mkdtemp(prefix="pulse-tests-")
# Environment must be set before any application import (settings are cached).
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{Path(_TMP, 'test.db').as_posix()}",
        "DB_AUTO_CREATE": "true",
        "TOMTOM_API_KEY": "",  # never use the real key in unit tests
        "JWT_SECRET": "test-secret-" + "x" * 40,
        "OSRM_URL": "http://osrm-car.test",
        "OSRM_FOOT_URL": "http://osrm-foot.test",
        "OSRM_BICYCLE_URL": "http://osrm-bicycle.test",
        "GEOCODE_FALLBACK_ENABLED": "false",
        "LOG_LEVEL": "WARNING",
        "CORS_ORIGINS": "http://localhost:3000",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from auth.security import hash_password  # noqa: E402
from db.models import Base, User  # noqa: E402
from db.session import get_engine, session_scope  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs live local services (OSRM/PostGIS)")


@pytest.fixture(autouse=True)
def clean_db():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from api import auth as auth_api

    auth_api.limiter._attempts.clear()
    from routing import engine as routing_engine

    routing_engine._TIMING_CACHE.clear()
    yield


@pytest.fixture
def app():
    import main

    return main.app


@pytest.fixture
def client(app):
    return TestClient(app)


def make_user(email="user@example.com", password="Correct-Horse-9", role="user", name="Test User") -> int:
    with session_scope() as s:
        u = User(email=email, password_hash=hash_password(password), display_name=name, role=role)
        s.add(u)
        s.flush()
        return u.id


def login(client, email="user@example.com", password="Correct-Horse-9") -> dict:
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def user_headers(client):
    make_user()
    return login(client)


@pytest.fixture
def admin_headers(client):
    make_user("admin@example.com", "Admin-Pass-123", role="admin", name="Admin")
    return login(client, "admin@example.com", "Admin-Pass-123")
