"""Place search and reverse geocoding."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import settings_dep
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
    result["attribution"] = "© OpenStreetMap contributors (ODbL)" + (
        "; Photon by komoot" if "photon" in result["sources"] else ""
    )
    return result


@router.get("/reverse")
def reverse(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
):
    return service.reverse(db, lat, lon)
