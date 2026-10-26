"""Build the place-search gazetteer from the local OpenStreetMap extract.

    python -m geocoding.gazetteer ../data/osm/bengaluru.osm.pbf

Extracts named localities, transit stations, landmarks, points of interest,
shops, offices, streets and named buildings with a representative coordinate,
assigns each the nearest locality name, and (re)loads the `places` table.
Data © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import argparse
import logging
import math
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import osmium
from sqlalchemy import delete, insert

from core.log_config import configure_logging
from db.models import Place
from db.session import init_db, session_scope
from geocoding.text import normalize

logger = logging.getLogger("pulse.gazetteer")

PLACE_IMPORTANCE = {
    "city": 1.0, "town": 0.85, "suburb": 0.8, "quarter": 0.7, "neighbourhood": 0.65,
    "village": 0.6, "locality": 0.55, "hamlet": 0.45,
}
AMENITY_IMPORTANCE = {
    "hospital": 0.6, "university": 0.6, "college": 0.5, "bus_station": 0.6, "school": 0.4,
    "police": 0.4, "townhall": 0.5, "cinema": 0.45, "marketplace": 0.5, "place_of_worship": 0.4,
    "fuel": 0.35, "bank": 0.3, "restaurant": 0.3, "cafe": 0.3, "fast_food": 0.25, "clinic": 0.35,
    "pharmacy": 0.3, "atm": 0.15, "library": 0.4, "community_centre": 0.35,
}

def classify(tags) -> Optional[Tuple[str, str, float]]:
    """(category, subcategory, importance) for a tagged OSM object, or None."""

    name = (tags.get("name:en") or tags.get("name") or "").lower()
    if "international airport" in name and "bus" not in name and "halt" not in name:
        return "transit", "airport", 0.98
    if "place" in tags and tags["place"] in PLACE_IMPORTANCE:
        return "locality", tags["place"], PLACE_IMPORTANCE[tags["place"]]
    if tags.get("aeroway") in ("aerodrome", "terminal"):
        return "transit", "airport", 0.95
    if tags.get("railway") in ("station", "halt") or tags.get("public_transport") == "station":
        sub = "metro" if tags.get("station") == "subway" or tags.get("subway") == "yes" else "rail"
        return "transit", sub, 0.75
    if "amenity" in tags:
        sub = tags["amenity"]
        return "poi", sub, AMENITY_IMPORTANCE.get(sub, 0.25)
    if "shop" in tags:
        return "shop", tags["shop"], 0.3 if tags["shop"] == "mall" else 0.25
    if "tourism" in tags or "historic" in tags:
        return "landmark", tags.get("tourism") or tags.get("historic"), 0.55
    if tags.get("leisure") in ("park", "stadium", "garden", "sports_centre"):
        return "landmark", tags["leisure"], 0.5
    if "office" in tags:
        return "office", tags["office"], 0.35
    if tags.get("landuse") in ("commercial", "retail", "industrial"):
        return "area", tags["landuse"], 0.4
    if "building" in tags:
        return "building", tags["building"], 0.2
    if tags.get("highway") == "bus_stop":
        if "=>" in name or ":" in name:  # BMTC route descriptions, not place names
            return None
        return "transit", "bus_stop", 0.28
    if "highway" in tags and tags["highway"] not in ("traffic_signals", "crossing", "street_lamp", "stop", "give_way"):
        return "street", tags["highway"], 0.35
    return None


def classify_untagged(tags) -> Optional[Tuple[str, str, float]]:
    """Named node with no recognised feature tag (e.g. the airport label node)."""

    ignored = {"name", "name:en", "name:kn", "alt_name", "source", "created_by", "note", "fixme", "wikidata", "wikipedia"}
    if all(k in ignored or k.startswith("name:") for k, _ in tags):
        return "poi", None, 0.3
    return None


class Extractor(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.places: List[dict] = []
        self.streets: Dict[Tuple[str, int, int], dict] = {}
        self.localities: List[Tuple[float, float, str, float]] = []

    def _add(self, osm_type: str, osm_id: int, tags, lat: float, lon: float) -> None:
        name = tags.get("name:en") or tags.get("name")
        if not name or len(name) > 200:
            return
        kind = classify(tags)
        if kind is None and osm_type == "n":
            kind = classify_untagged(tags)
        if kind is None:
            return
        category, sub, importance = kind
        alt = [tags.get(k) for k in ("name", "alt_name", "old_name", "short_name", "official_name", "name:kn") if tags.get(k)]
        record = {
            "osm_type": osm_type, "osm_id": osm_id, "name": name.strip(),
            "name_normalized": normalize(name)[:200], "alt_names": " | ".join(sorted(set(alt) - {name}))[:2000] or None,
            "category": category, "subcategory": (sub or "")[:48] or None, "lat": lat, "lon": lon,
            "importance": importance,
        }
        if category == "street":
            # One representative per street name per ~1 km cell (streets are many ways).
            key = (record["name_normalized"], int(lat * 100), int(lon * 100))
            prev = self.streets.get(key)
            if prev is None or (tags["highway"] in ("trunk", "primary", "secondary") and prev["importance"] < 0.45):
                if tags["highway"] in ("motorway", "trunk", "primary"):
                    record["importance"] = 0.5
                elif tags["highway"] == "secondary":
                    record["importance"] = 0.42
                self.streets[key] = record
            return
        if category == "locality":
            self.localities.append((lat, lon, name.strip(), importance))
        self.places.append(record)

    def node(self, n) -> None:
        if n.tags and n.location.valid():
            self._add("n", n.id, n.tags, n.location.lat, n.location.lon)

    def way(self, w) -> None:
        if not w.tags or "name" not in w.tags:
            return
        lats, lons = [], []
        for node in w.nodes:
            if node.location.valid():
                lats.append(node.location.lat)
                lons.append(node.location.lon)
        if not lats:
            return
        mid = len(lats) // 2
        if "highway" in w.tags:  # use an on-road point, not the bbox centre
            lat, lon = lats[mid], lons[mid]
        else:
            lat, lon = sum(lats) / len(lats), sum(lons) / len(lons)
        self._add("w", w.id, w.tags, lat, lon)


def assign_localities(records: List[dict], localities: List[Tuple[float, float, str, float]]) -> None:
    neighbourhoods = [loc for loc in localities if loc[3] < 1.0]  # skip the city node itself
    grid: Dict[Tuple[int, int], list] = defaultdict(list)
    for loc in neighbourhoods:
        grid[(int(loc[0] * 50), int(loc[1] * 50))].append(loc)
    for rec in records:
        if rec["category"] == "locality":
            rec["locality"] = None
            continue
        gx, gy = int(rec["lat"] * 50), int(rec["lon"] * 50)
        best, best_d = None, 3500.0
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for lat, lon, name, _ in grid.get((gx + dx, gy + dy), ()):
                    d = math.hypot((lat - rec["lat"]) * 111_000, (lon - rec["lon"]) * 108_000)
                    if d < best_d:
                        best, best_d = name, d
        rec["locality"] = best


COPY_COLUMNS = (
    "osm_type", "osm_id", "name", "name_normalized", "alt_names", "category",
    "subcategory", "locality", "lat", "lon", "importance",
)


def _copy_rows(session, rows: List[dict]) -> None:
    """Bulk load with PostgreSQL COPY (orders of magnitude faster than INSERTs)."""

    raw = session.connection().connection.driver_connection
    with raw.cursor() as cursor:
        with cursor.copy(f"COPY places ({', '.join(COPY_COLUMNS)}) FROM STDIN") as copy:
            for r in rows:
                copy.write_row([r.get(c) for c in COPY_COLUMNS])


def build(pbf_path: str) -> int:
    started = time.time()
    extractor = Extractor()
    extractor.apply_file(pbf_path, locations=True)
    records = extractor.places + list(extractor.streets.values())
    assign_localities(records, extractor.localities)
    # De-duplicate identical OSM ids (a node may appear twice via different handlers).
    unique = {(r["osm_type"], r["osm_id"]): r for r in records}
    rows = list(unique.values())
    logger.info("Extracted %d places in %.1fs", len(rows), time.time() - started)
    with session_scope() as session:
        session.execute(delete(Place))
        if session.bind.dialect.name == "postgresql":
            _copy_rows(session, rows)
        else:
            for i in range(0, len(rows), 5000):
                session.execute(insert(Place), rows[i : i + 5000])
    logger.info("Loaded gazetteer in %.1fs", time.time() - started)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", help="OSM .pbf extract (e.g. data/osm/bengaluru.osm.pbf)")
    parser.add_argument("--create-tables", action="store_true", help="create tables first (SQLite dev)")
    args = parser.parse_args()
    configure_logging("INFO")
    if args.create_tables:
        init_db()
    print(f"places loaded: {build(args.pbf)}")


if __name__ == "__main__":
    main()
