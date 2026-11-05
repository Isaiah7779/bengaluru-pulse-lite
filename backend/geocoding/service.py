"""Place search (autocomplete) and reverse geocoding.

Order of resolution:
1. Coordinates typed by the user ("12.97, 77.59", "12°58'N 77°35'E").
2. Photon (komoot): OpenStreetMap search over addresses (house numbers where
   mapped), streets, buildings, apartments, layouts and POIs. Restricted to the
   Bengaluru bounding box, biased to the other route endpoint, cached for an hour,
   concurrency-capped and backed off on HTTP 429 (fair use of the public instance;
   point PHOTON_URL at a self-hosted Photon to extend coverage/limits).
3. Local OSM gazetteer (`places` table), merged in when it has been built
   (`python -m geocoding.gazetteer`); hosted deployments usually have none.
Nominatim is never used for autocomplete (forbidden by its usage policy).
A Photon failure is reported to the caller, never turned into "no match".
"""

from __future__ import annotations

import asyncio
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


class GeocoderUnavailable(Exception):
    """Photon failed: network error, timeout, HTTP error or rate limit."""

    def __init__(self, reason: str, rate_limited: bool = False):
        super().__init__(reason)
        self.reason = reason
        self.rate_limited = rate_limited


# The public Photon instance is fair-use: cache answers, cap concurrency, back off on 429.
_PHOTON_TTL_S = 3600
_PHOTON_CACHE_MAX = 2000
_PHOTON_SLOTS = asyncio.Semaphore(4)
_PHOTON_STATE = {"backoff_until": 0.0}
BENGALURU_CENTER = (12.9716, 77.5946)


def _cache_get(key: str):
    hit = _PHOTON_CACHE.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    return None


def _cache_put(key: str, value) -> None:
    if len(_PHOTON_CACHE) >= _PHOTON_CACHE_MAX:
        now = time.monotonic()
        stale = [k for k, (exp, _) in _PHOTON_CACHE.items() if exp <= now]
        for k in stale or list(_PHOTON_CACHE)[: _PHOTON_CACHE_MAX // 4]:
            _PHOTON_CACHE.pop(k, None)
    _PHOTON_CACHE[key] = (time.monotonic() + _PHOTON_TTL_S, value)


def photon_enabled(settings: Settings) -> bool:
    return bool(settings.geocode_fallback_enabled and settings.photon_url)


async def _photon_get(settings: Settings, path: str, params: Dict[str, Any]) -> List[dict]:
    if time.monotonic() < _PHOTON_STATE["backoff_until"]:
        raise GeocoderUnavailable("rate_limited", rate_limited=True)
    try:
        async with _PHOTON_SLOTS:
            async with async_client(settings.geocode_timeout_seconds) as client:
                response = await client.get(settings.photon_url.rstrip("/") + path, params=params)
        if response.status_code == 429:
            _PHOTON_STATE["backoff_until"] = time.monotonic() + 30
            logger.warning("Photon %s rate-limited (HTTP 429); backing off 30 s", path)
            raise GeocoderUnavailable("rate_limited", rate_limited=True)
        response.raise_for_status()
        return response.json().get("features", [])
    except GeocoderUnavailable:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        detail = f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__
        logger.warning("Photon %s failed: %s", path, detail)
        raise GeocoderUnavailable(detail) from exc


def _photon_result(f: dict, near: Optional[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
    props = f.get("properties") or {}
    coords = (f.get("geometry") or {}).get("coordinates") or []
    if len(coords) != 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    house, street = props.get("housenumber"), props.get("street")
    street_line = " ".join(filter(None, [house, street])) or None
    name = props.get("name") or street_line
    if not name:
        return None
    area = props.get("locality") or props.get("district")
    parts = [name]
    for part in (street_line, area, props.get("city") or props.get("county"), props.get("postcode")):
        if part and part not in parts:
            parts.append(part)
    osm_key, osm_value = props.get("osm_key") or "place", props.get("osm_value") or "place"
    if house and not props.get("name"):
        category_label = "Address"
    elif osm_key == "highway" and osm_value not in ("bus_stop", "platform"):
        category_label = "Street"
    else:
        category_label = osm_value.replace("_", " ").title()
    return {
        "id": f"photon:{props.get('osm_type', '')}{props.get('osm_id', '')}",
        "name": name,
        "label": ", ".join(parts),
        "address": ", ".join(parts[1:]) or None,
        "category": osm_key,
        "category_label": category_label,
        "subcategory": osm_value,
        "locality": area,
        "housenumber": house,
        "street": street,
        "postcode": props.get("postcode"),
        "lat": lat,
        "lon": lon,
        "distance_m": round(haversine_m((near[1], near[0]), (lon, lat))) if near else None,
        "score": 0.0,
        "source": "photon",
    }


async def search_photon(settings: Settings, query: str, limit: int, near: Optional[Tuple[float, float]]) -> List[Dict[str, Any]]:
    """OSM address/street/POI search via Photon inside Bengaluru; raises GeocoderUnavailable on failure."""

    if not photon_enabled(settings):
        return []
    bias = near or BENGALURU_CENTER
    key = f"s|{normalize(query)}|{limit}|{bias[0]:.2f},{bias[1]:.2f}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    params: Dict[str, Any] = {
        "q": query, "limit": min(limit * 2, 20), "lang": "en", "bbox": ",".join(map(str, BBOX)),
        "lat": bias[0], "lon": bias[1],
    }
    features = await _photon_get(settings, "/api/", params)
    results, seen = [], set()
    for f in features:
        r = _photon_result(f, near)
        if r is None or not in_bengaluru(r["lat"], r["lon"]):
            continue
        # One feature can come back as node + way + relation: keep one per label and spot.
        dedupe = (r["label"].lower(), round(r["lat"], 3), round(r["lon"], 3))
        if dedupe in seen:
            continue
        seen.add(dedupe)
        results.append(r)
        if len(results) >= limit:
            break
    _cache_put(key, results)
    return results


async def reverse_photon(settings: Settings, lat: float, lon: float) -> Optional[Dict[str, Any]]:
    if not photon_enabled(settings):
        return None
    key = f"r|{lat:.5f},{lon:.5f}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    features = await _photon_get(settings, "/reverse", {"lat": lat, "lon": lon, "lang": "en", "limit": 1})
    result = _photon_result(features[0], (lat, lon)) if features else None
    _cache_put(key, result)
    return result


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
            "unavailable": [],
            "rate_limited": False,
        }
    is_pg = not settings.is_sqlite
    local = search_local(db, query, limit, near, is_postgres=is_pg)
    remote: List[Dict[str, Any]] = []
    unavailable: List[str] = []
    rate_limited = False
    if len(query) >= settings.geocode_min_chars:
        try:
            remote = await search_photon(settings, query, limit, near)
        except GeocoderUnavailable as exc:
            unavailable.append("photon")
            rate_limited = exc.rate_limited
    # Interleave Photon (city-wide addresses) with local gazetteer hits, minus duplicates.
    known = {(round(r["lat"], 3), round(r["lon"], 3)) for r in remote}
    local = [r for r in local if (round(r["lat"], 3), round(r["lon"], 3)) not in known]
    merged: List[Dict[str, Any]] = []
    for i in range(max(len(remote), len(local))):
        merged.extend(rows[i] for rows in (remote, local) if i < len(rows))
    sources = [name for name, rows in (("photon", remote), ("openstreetmap", local)) if rows]
    return {
        "query": query,
        "results": merged[:limit],
        "sources": sources,
        # Lets callers tell "no such place" apart from "the geocoder failed".
        "unavailable": unavailable,
        "rate_limited": rate_limited,
    }


def reverse_local(db: Session, lat: float, lon: float) -> Dict[str, Any]:
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


async def reverse(db: Session, settings: Settings, lat: float, lon: float) -> Dict[str, Any]:
    """Address of a map point: Photon reverse when reachable, else the local gazetteer."""

    local = reverse_local(db, lat, lon)
    if local.get("nearest_feature_m") is not None and local["nearest_feature_m"] <= 30:
        return local
    try:
        hit = await reverse_photon(settings, lat, lon)
    except GeocoderUnavailable:
        return local
    if not hit:
        return local
    distance = haversine_m((lon, lat), (hit["lon"], hit["lat"]))
    if distance > 250:
        return local
    return {
        "lat": lat,
        "lon": lon,
        "name": hit["name"],
        "label": hit["label"],
        "locality": hit["locality"] or local.get("locality"),
        "nearest_feature_m": round(distance),
        "within_bengaluru": in_bengaluru(lat, lon),
        "source": "photon",
    }
