"""Liveness and readiness endpoints."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.deps import settings_dep
from core.settings import Settings
from db.session import session_scope
from providers.quota import QuotaGuard
from routing.osrm_client import OSRMClient
from traffic.state_engine import freshness_report

router = APIRouter(tags=["health"])
_STARTED = time.monotonic()


@router.get("/health")
def health(settings: Settings = Depends(settings_dep)):
    """Liveness: the process is up. Dependencies are checked by /health/ready."""

    return {
        "status": "ok",
        "version": settings.app_version,
        "uptime_s": round(time.monotonic() - _STARTED),
    }


async def dependency_report(settings: Settings) -> dict:
    checks: dict = {}

    def db_check():
        with session_scope() as s:
            s.execute(text("SELECT 1"))

    try:
        await asyncio.to_thread(db_check)
        checks["database"] = {"status": "ok", "dialect": "sqlite" if settings.is_sqlite else "postgresql"}
    except Exception as exc:
        checks["database"] = {"status": "down", "error": type(exc).__name__}

    async def osrm(name: str, url):
        if not url:
            return name, {"status": "not_configured"}
        ok = await OSRMClient(url, timeout=3.0).health()
        return name, {"status": "ok" if ok else "down"}

    for name, value in await asyncio.gather(
        osrm("osrm_car", settings.osrm_url),
        osrm("osrm_foot", settings.osrm_foot_url),
        osrm("osrm_bicycle", settings.osrm_bicycle_url),
    ):
        checks[name] = value

    if settings.tomtom_key:
        try:
            guard = QuotaGuard("tomtom", settings.tomtom_daily_budget)
            used = await asyncio.to_thread(guard.used_today)
            checks["tomtom"] = {"status": "ok", "used_today": used, "daily_budget": settings.tomtom_daily_budget}
        except Exception as exc:
            checks["tomtom"] = {"status": "unknown", "error": type(exc).__name__}
    else:
        checks["tomtom"] = {"status": "not_configured"}

    if checks["database"]["status"] == "ok":
        try:
            def fresh():
                with session_scope() as s:
                    return freshness_report(s, settings.observation_stale_minutes)

            report = await asyncio.to_thread(fresh)
            t = report["traffic"]
            checks["traffic_data"] = {
                "status": "ok" if t["segments_fresh"] else ("stale" if t["observations_total"] else "no_data"),
                "fresh_segments": t["segments_fresh"],
                "last_observation_at": t["last_observation_at"],
            }
        except Exception as exc:
            checks["traffic_data"] = {"status": "unknown", "error": type(exc).__name__}
    return checks


@router.get("/health/ready")
async def ready(settings: Settings = Depends(settings_dep)):
    """Readiness: database and car routing must be up; others reported as degraded."""

    checks = await dependency_report(settings)
    critical_ok = checks["database"]["status"] == "ok" and checks["osrm_car"]["status"] == "ok"
    degraded = [k for k, v in checks.items() if v.get("status") not in ("ok", "not_configured")]
    body = {
        "status": "ok" if critical_ok and not degraded else ("degraded" if critical_ok else "down"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    return JSONResponse(status_code=200 if critical_ok else 503, content=body)
