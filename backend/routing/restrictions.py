"""Mode restrictions the routing graph does not model (motorcycle=no on the car graph).

Motorcycles are routed on the car graph (OSRM has no motorcycle profile), and
car.lua ignores the OSM ``motorcycle=*`` tag. Ways tagged ``motorcycle=no``
(e.g. the Bengaluru-Mysuru Expressway main carriageway) would otherwise be
recommended to two-wheelers.

``motorcycle_restricted.json`` lists those ways, extracted from the same
OpenStreetMap extract as the graphs:

    python -m routing.restrictions build ../data/osm/bengaluru.osm.pbf

A route uses a restricted way when consecutive route coordinates are
consecutive nodes of such a way (OSRM ``overview=full`` geometry is made of OSM
node positions), or, for servers whose OSM data differs slightly from the
extract, when a continuous stretch of the route runs within a few metres of it.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from routing.geometry import PointIndex, haversine_m, resample

DATA_FILE = Path(__file__).with_name("motorcycle_restricted.json")

# Highway classes car.lua routes; motorcycle=no on others (footways) cannot be reached anyway.
CAR_ROUTABLE = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
    "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service",
}

EXACT_MIN_M = 50.0  # ignore touching a restricted way at a junction
NEAR_TOLERANCE_M = 8.0  # parallel service roads run further away than this
NEAR_SPACING_M = 20.0
NEAR_MIN_RUN_M = 300.0

NodeKey = Tuple[int, int]


def _key(lon: float, lat: float) -> NodeKey:
    return (round(lon * 1e6), round(lat * 1e6))


@dataclass
class RestrictedWays:
    """Ways a mode may not use, with fast exact and near-match lookups."""

    tag: str
    source: str
    ways: List[Dict[str, object]]
    _segments: Set[FrozenSet[NodeKey]] = field(default_factory=set, repr=False)
    _index: Optional[PointIndex] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        points = []
        for way in self.ways:
            coords = way["coordinates"]
            for a, b in zip(coords, coords[1:]):
                self._segments.add(frozenset((_key(*a), _key(*b))))
            points.extend(resample(coords, 4.0))
        self._index = PointIndex(points, cell_m=25.0) if points else None

    @property
    def count(self) -> int:
        return len(self.ways)

    def exact_length_m(self, coords: Sequence[Sequence[float]]) -> float:
        total = 0.0
        for a, b in zip(coords, coords[1:]):
            if frozenset((_key(a[0], a[1]), _key(b[0], b[1]))) in self._segments:
                total += haversine_m(a, b)
        return total

    def near_length_m(self, coords: Sequence[Sequence[float]]) -> float:
        """Length of continuous runs (>= NEAR_MIN_RUN_M) lying within NEAR_TOLERANCE_M of a restricted way."""

        if self._index is None:
            return 0.0
        total = run = 0.0
        for p in resample(coords, NEAR_SPACING_M):
            if next(self._index.neighbours(p[0], p[1], NEAR_TOLERANCE_M), None) is not None:
                run += NEAR_SPACING_M
            else:
                total += run if run >= NEAR_MIN_RUN_M else 0.0
                run = 0.0
        total += run if run >= NEAR_MIN_RUN_M else 0.0
        return total

    def used_length_m(self, coords: Sequence[Sequence[float]]) -> float:
        exact = self.exact_length_m(coords)
        exact = exact if exact >= EXACT_MIN_M else 0.0
        return max(exact, self.near_length_m(coords))

    def stretches(self, coords: Sequence[Sequence[float]]) -> List[Tuple[int, int]]:
        """Index ranges [i, j] of route coordinates on restricted ways (exact matches)."""

        runs: List[Tuple[int, int]] = []
        start = None
        for i, (a, b) in enumerate(zip(coords, coords[1:])):
            hit = frozenset((_key(a[0], a[1]), _key(b[0], b[1]))) in self._segments
            if hit and start is None:
                start = i
            elif not hit and start is not None:
                runs.append((start, i))
                start = None
        if start is not None:
            runs.append((start, len(coords) - 1))
        return runs

    def names(self) -> List[str]:
        return sorted({str(w.get("name")) for w in self.ways if w.get("name")})


@lru_cache(maxsize=1)
def motorcycle_restrictions() -> Optional[RestrictedWays]:
    if not DATA_FILE.exists():
        return None
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return RestrictedWays(tag=data["tag"], source=data["source"], ways=data["ways"])


def bypass_waypoints(coords: Sequence[Sequence[float]], stretch: Tuple[int, int],
                     offsets_m: Sequence[float] = (80.0, -80.0, 200.0, -200.0)) -> List[List[Tuple[float, float]]]:
    """Single via-points beside the middle of a restricted stretch, as (lat, lon).

    OSRM snaps each to the nearest road, which next to an expressway is usually
    its service road, so the route is pulled off the restricted carriageway.
    """

    i, j = stretch
    i, j = max(0, i), min(len(coords) - 1, j)
    if j <= i:
        return []
    mid = (i + j) // 2
    a, b = coords[max(i, mid - 1)], coords[min(j, mid + 1)]
    lon, lat = coords[mid][0], coords[mid][1]
    m_lat = 111_320.0
    m_lon = 111_320.0 * math.cos(math.radians(lat))
    dx, dy = (b[0] - a[0]) * m_lon, (b[1] - a[1]) * m_lat
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    px, py = -dy / length, dx / length
    return [[(lat + py * off / m_lat, lon + px * off / m_lon)] for off in offsets_m]


def build(pbf: str, out: Path = DATA_FILE) -> int:
    """Extract car-routable ways tagged motorcycle=no from an OSM PBF (needs pyosmium)."""

    import osmium

    ways: List[Dict[str, object]] = []

    class Handler(osmium.SimpleHandler):
        def way(self, w):
            if w.tags.get("motorcycle") != "no" or w.tags.get("highway") not in CAR_ROUTABLE:
                return
            coords = [[round(n.location.lon, 7), round(n.location.lat, 7)] for n in w.nodes if n.location.valid()]
            if len(coords) >= 2:
                ways.append({"osm_id": w.id, "highway": w.tags.get("highway"),
                             "name": w.tags.get("name") or w.tags.get("ref"), "coordinates": coords})

    Handler().apply_file(pbf, locations=True)
    ways.sort(key=lambda w: w["osm_id"])
    payload = {
        "tag": "motorcycle=no",
        "source": f"OpenStreetMap contributors (ODbL), extracted from {Path(pbf).name}",
        "ways": ways,
    }
    out.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return len(ways)


if __name__ == "__main__":  # pragma: no cover - maintenance command
    if len(sys.argv) != 3 or sys.argv[1] != "build":
        sys.exit("usage: python -m routing.restrictions build <bengaluru.osm.pbf>")
    print(f"{build(sys.argv[2])} motorcycle=no ways written to {DATA_FILE}")
    from routing import access

    meta = access.build(sys.argv[2])
    print(f"{meta['ways']} access-restricted ways ({meta['segments']} segments) written to {access.DATA_FILE}")
