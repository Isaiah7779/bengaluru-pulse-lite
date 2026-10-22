"""FastAPI application for Bengaluru Pulse.

Run:  python -m uvicorn main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from core.errors import install_error_handlers
from core.log_config import configure_logging
from core.settings import get_settings
from db.session import init_db

logger = logging.getLogger("pulse")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)

    if settings.db_auto_create:
        init_db()

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    install_error_handlers(app)

    from api import admin, auth, community, forecast_api, geocode, health, legacy, me, routing_api, traffic_api

    for module in (health, auth, me, routing_api, geocode, traffic_api, forecast_api, community, admin, legacy):
        app.include_router(module.router)

    logger.info(
        "Bengaluru Pulse API %s started (env=%s, db=%s)",
        settings.app_version,
        settings.environment,
        "sqlite" if settings.is_sqlite else "postgresql",
    )
    return app


app = create_app()
