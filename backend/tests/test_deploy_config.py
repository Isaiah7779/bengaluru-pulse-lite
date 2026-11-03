"""Free-tier deployment settings: CORS for hosted frontends."""

import pytest
from fastapi.testclient import TestClient

from core.settings import Settings, get_settings

PREVIEW_REGEX = r"^https://bengaluru-pulse(-[a-z0-9-]+)?\.vercel\.app$"


@pytest.fixture
def regex_app(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", PREVIEW_REGEX)
    get_settings.cache_clear()
    import main

    yield main.create_app()
    get_settings.cache_clear()


def preflight(client, origin):
    return client.options(
        "/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )


def test_cors_allows_listed_and_regex_origins_only(regex_app):
    client = TestClient(regex_app)
    for origin in ("http://localhost:3000", "https://bengaluru-pulse.vercel.app", "https://bengaluru-pulse-git-v2-abc.vercel.app"):
        response = preflight(client, origin)
        assert response.status_code == 200, origin
        assert response.headers["access-control-allow-origin"] == origin
    response = preflight(client, "https://evil.vercel.app")
    assert "access-control-allow-origin" not in response.headers


def test_production_rejects_match_all_cors_regex():
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="x" * 40, CORS_ORIGINS="https://a.example", cors_origin_regex=".*")
    Settings(environment="production", jwt_secret="x" * 40, CORS_ORIGINS="https://a.example", cors_origin_regex=PREVIEW_REGEX)
