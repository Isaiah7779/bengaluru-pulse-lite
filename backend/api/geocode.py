"""Place search and reverse geocoding."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import settings_dep
from core.errors import UpstreamUnavailable
from core.settings import Settings
from db.session import get_db
from geocoding import service

router = APIRouter(prefix="/v1/geocode", tags=["geocoding"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=120),
    limit: int = Query(8, ge=1, le=20),
    near_lat: Optional[float] = Query(None, ge=-90, le=90),
    near_lon: Optional[float] = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    near = (near_lat, near_lon) if near_lat is not None and near_lon is not None else None
    result = await service.search(db, settings, q, limit, near)
    if not result["results"] and result["unavailable"]:
        # Nothing found and the address geocoder failed: an outage, never "no match".
        if result["rate_limited"]:
            raise UpstreamUnavailable(
                "Place search is busy right now. Wait a few seconds and try again, or pick the place on the map.",
                code="geocoder_rate_limited",
            )
        raise UpstreamUnavailable(
            "Place search is temporarily unavailable. Try again shortly or pick the place on the map.",
            code="geocoder_unavailable",
        )
    result["attribution"] = "© OpenStreetMap contributors (ODbL)" + (
        "; search by Photon (komoot)" if "photon" in result["sources"] else ""
    )
    return result


@router.get("/reverse")
async def reverse(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    return await service.reverse(db, settings, lat, lon)
