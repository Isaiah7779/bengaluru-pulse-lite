"""Place search (autocomplete) and reverse geocoding.

Order of resolution:
1. Coordinates typed by the user ("12.97, 77.59", "12°58'N 77°35'E").
2. Local OSM gazetteer (`places` table) — self-hosted, no third-party quota.
3. Photon (komoot) fallback when local results are thin, restricted to the
   Bengaluru bounding box and cached. Nominatim is never used for autocomplete
   (forbidden by its usage policy).
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from core.http import async_client
from core.settings import Settings
from db.models import Place
from geocoding.text import normalize
from routing.geometry import haversine_m

logger = logging.getLogger(__name__)

BBOX = (77.30, 12.70, 77.95, 13.30)  # lon/lat bounds accepted as "Bengaluru"
CATEGORY_LABEL = {
    "locality": "Area", "transit": "Transit", "poi": "Place", "shop": "Shop", "landmark": "Landmark",
    "office": "Office", "area": "Area", "building": "Building", "street": "Street",
}

_COORD_DEC = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_COORD_DMS = re.compile(
    r"(\d{1,2})[°\s]+(\d{1,2})['\s]+(\d{1,2}(?:\.\d+)?)?\"?\s*([NS])[,\s]+(\d{1,3})[°\s]+(\d{1,2})['\s]+(\d{1,2}(?:\.\d+)?)?\"?\s*([EW])",
    re.IGNORECASE,
)
_PHOTON_CACHE: Dict[str, Tuple[float, List[dict]]] = {}


def in_bengaluru(lat: float, lon: float) -> bool:
    return BBOX[1] <= lat <= BBOX[3] and BBOX[0] <= lon <= BBOX[2]


def parse_coordinates(text: str) -> Optional[Tuple[float, float]]:
    m = _COORD_DEC.match(text)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if -90 <= a <= 90 and -180 <= b <= 180:
            # Accept "lon,lat" if only that order lands in Bengaluru.
            if not in_bengaluru(a, b) and in_bengaluru(b, a):
                a, b = b, a
            return a, b
    m = _COORD_DMS.search(text)
    if m:
        def dms(d, mi, s, hemi):
            v = float(d) + float(mi) / 60 + float(s or 0) / 3600
            return -v if hemi.upper() in "SW" else v

        return dms(*m.group(1, 2, 3, 4)), dms(*m.group(5, 6, 7, 8))
    return None


def _result(place: Place, score: float, distance_m: Optional[float] = None) -> Dict[str, Any]:
    context = ", ".join(filter(None, [place.locality, "Bengaluru"]))
    return {
        "id": f"osm:{place.osm_type}{place.osm_id}",
        "name": place.name,
        "label": f"{place.name}, {context}" if place.category != "locality" else f"{place.name}, Bengaluru",
        "category": place.category,
        "category_label": CATEGORY_LABEL.get(place.category, place.category),
        "subcategory": place.subcategory,
        "locality": place.locality,
        "lat": place.lat,
        "lon": place.lon,
        "distance_m": round(distance_m) if distance_m is not None else None,
        "score": round(score, 4),
        "source": "openstreetmap",
    }


def search_local(
    db: Session, query: str, limit: int = 8, near: Optional[Tuple[float, float]] = None, is_postgres: bool = False
) -> List[Dict[str, Any]]:
    norm = normalize(query)
    tokens = [t for t in norm.split() if t]
    if not tokens:
        return []
    # Every token must occur as a word prefix in the name (or alt names).
    conditions = []
    for t in tokens[:6]:
        conditions.append(
            or_(
                Place.name_normalized.like(f"{t}%"),
                Place.name_normalized.like(f"% {t}%"),
                func.lower(func.coalesce(Place.alt_names, "")).like(f"%{t}%"),
            )
        )
    stmt = select(Place).where(and_(*conditions))
    if is_postgres:
        stmt = stmt.order_by(func.similarity(Place.name_normalized, norm).desc(), Place.importance.desc())
    else:
        stmt = stmt.order_by(Place.importance.desc())
    candidates = db.scalars(stmt.limit(300)).all()

    ranked = []
    for p in candidates:
        score = p.importance
        if p.name_normalized == norm:
            score += 1.0
        elif p.name_normalized.startswith(norm):
            score += 0.6
        # Prefer shorter names that match fully (less noise).
        score += 0.3 * (len(norm) / max(len(p.name_normalized), 1))
        distance = None
        if near:
            distance = haversine_m((near[1], near[0]), (p.lon, p.lat))
            score += 0.4 * math.exp(-distance / 8000)
        ranked.append((score, distance, p))
    ranked.sort(key=lambda r: -r[0])

    out, seen = [], set()
    for score, distance, p in ranked:
        # Localities are often mapped as several nodes; merge same-name ones within ~1 km.
        precision = 2 if p.category == "locality" else 3
        key = (p.name_normalized, p.category == "locality", round(p.lat, precision), round(p.lon, precision))
        if key in seen:
            continue
        seen.add(key)
        out.append(_result(p, score, distance))
        if len(out) >= limit:
            break
    return out


async def search_photon(settings: Settings, query: str, limit: int, near: Optional[Tuple[float, float]]) -> List[Dict[str, Any]]:
    if not settings.geocode_fallback_enabled or not settings.photon_url:
        return []
    key = f"{query.lower()}|{limit}"
    hit = _PHOTON_CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    params: Dict[str, Any] = {"q": query, "limit": limit, "lang": "en", "bbox": ",".join(map(str, BBOX))}
    if near:
        params.update(lat=near[0], lon=near[1])
    try:
        async with async_client(5.0) as client:
            response = await client.get(
                settings.photon_url.rstrip("/") + "/api/",
                params=params,
                headers={"User-Agent": "BengaluruPulse/3.0 (academic project)"},
            )
        response.raise_for_status()
        features = response.json().get("features", [])
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Photon fallback failed: %s", type(exc).__name__)
        return []
    results = []
    for f in features:
        props = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) != 2 or not props.get("name"):
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not in_bengaluru(lat, lon):
            continue
        context = ", ".join(filter(None, [props.get("street"), props.get("district") or props.get("locality"), props.get("city")]))
        results.append(
            {
                "id": f"photon:{props.get('osm_type', '')}{props.get('osm_id', '')}",
                "name": props["name"],
                "label": f"{props['name']}, {context}" if context else props["name"],
                "category": props.get("osm_key") or "place",
                "category_label": (props.get("osm_value") or "place").replace("_", " ").title(),
                "subcategory": props.get("osm_value"),
                "locality": props.get("district") or props.get("locality"),
                "lat": lat,
                "lon": lon,
                "distance_m": round(haversine_m((near[1], near[0]), (lon, lat))) if near else None,
                "score": 0.0,
                "source": "photon",
            }
        )
    _PHOTON_CACHE[key] = (time.monotonic() + 3600, results)
    return results


async def search(
    db: Session, settings: Settings, query: str, limit: int = 8, near: Optional[Tuple[float, float]] = None
) -> Dict[str, Any]:
    query = query.strip()
    coords = parse_coordinates(query)
    if coords:
        lat, lon = coords
        return {
            "query": query,
            "results": [
                {
                    "id": f"coord:{lat:.6f},{lon:.6f}",
                    "name": f"{lat:.5f}, {lon:.5f}",
                    "label": f"Coordinates {lat:.5f}, {lon:.5f}",
                    "category": "coordinates",
                    "category_label": "Coordinates",
                    "lat": lat,
                    "lon": lon,
                    "source": "input",
                    "within_bengaluru": in_bengaluru(lat, lon),
                }
            ],
            "sources": ["input"],
        }
    is_pg = not settings.is_sqlite
    local = search_local(db, query, limit, near, is_postgres=is_pg)
    sources = ["openstreetmap"] if local else []
    if len(local) < min(3, limit) and len(query) >= 3:
        remote = await search_photon(settings, query, limit, near)
        known = {(round(r["lat"], 3), round(r["lon"], 3)) for r in local}
        extra = [r for r in remote if (round(r["lat"], 3), round(r["lon"], 3)) not in known]
        if extra:
            sources.append("photon")
        local += extra[: max(limit - len(local), 0)]
    return {"query": query, "results": local, "sources": sources}


def reverse(db: Session, lat: float, lon: float) -> Dict[str, Any]:
    """Nearest named feature, preferring POIs/streets within 150 m, plus locality."""

    delta = 0.004
    rows = db.scalars(
        select(Place).where(Place.lat.between(lat - delta, lat + delta), Place.lon.between(lon - delta, lon + delta))
    ).all()
    best, best_d = None, math.inf
    for p in rows:
        d = haversine_m((lon, lat), (p.lon, p.lat))
        if p.category == "locality":
            continue
        if d < best_d:
            best, best_d = p, d
    locality = None
    loc_rows = db.scalars(
        select(Place).where(
            Place.category == "locality",
            Place.lat.between(lat - 0.03, lat + 0.03),
            Place.lon.between(lon - 0.03, lon + 0.03),
        )
    ).all()
    if loc_rows:
        locality = min(loc_rows, key=lambda p: haversine_m((lon, lat), (p.lon, p.lat))).name
    if best is not None and best_d <= 150:
        name = best.name
        label = ", ".join(filter(None, [name, locality, "Bengaluru"]))
    else:
        name = locality or f"{lat:.5f}, {lon:.5f}"
        label = ", ".join(filter(None, [f"Near {locality}" if locality else name, "Bengaluru"]))
    return {
        "lat": lat,
        "lon": lon,
        "name": name,
        "label": label,
        "locality": locality,
        "nearest_feature_m": round(best_d) if best is not None and best_d != math.inf else None,
        "within_bengaluru": in_bengaluru(lat, lon),
        "source": "openstreetmap",
    }
