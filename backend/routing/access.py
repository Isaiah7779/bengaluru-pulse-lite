"""Private and destination-only road detection that does not depend on OSRM road classes.

Why this exists
---------------
car.lua marks private / destination-only ways with the OSRM class
``restricted`` and lets a route use them only to start or end a leg. A
via-point snapped inside a gated campus (e.g. RMZ Ecospace, Bellandur) or a
gated layout therefore pulls the whole route through it. Our own OSRM servers
report that class on every step, but the public FOSSGIS server
(routing.openstreetmap.de) returns no ``classes`` at all, so on Render the
class alone cannot verify anything.

What this module checks
-----------------------
``car_access_restricted.bin`` holds a 64-bit hash of every road segment
(consecutive node pair) of a car-routable OSM way whose effective motor-car
access is one of ``RESTRICTED_VALUES``. Effective access follows car.lua's tag
order: ``motorcar``, then ``motor_vehicle``, ``vehicle``, ``access``. Ways with
``access=private`` but ``motor_vehicle=yes`` are therefore public for cars.

A route segment counts only when it is *exactly* such a segment: OSRM's
``overview=full`` geometry is made of OSM node positions, so a road beside a
campus, or a public road crossing it at a gate, is never matched by proximity.
Private stretches at the very start or end of a trip are allowed: that is the
traveller's own origin or destination.

Limits (documented, not hidden)
-------------------------------
* Only what OpenStreetMap tags is known. Gated roads without an access tag,
  and gates (``barrier=gate``) on otherwise public roads, are not treated as
  private.
* The file reflects the extract it was built from. A road edited in OSM after
  that, and served by a public OSRM with newer data, can be missed (its node
  positions no longer match). Rebuild the file whenever the graphs are rebuilt:

      python -m routing.restrictions build ../data/osm/bengaluru.osm.pbf
"""

from __future__ import annotations

import hashlib
import json
from array import array
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from routing.geometry import haversine_m

DATA_FILE = Path(__file__).with_name("car_access_restricted.bin")
META_FILE = Path(__file__).with_name("car_access_restricted.json")

# car.lua's restricted_access_tag_list minus "unknown" (too vague to call a road private).
RESTRICTED_VALUES = {"private", "destination", "customers", "delivery", "permit", "residents"}
ACCESS_KEYS = ("motorcar", "motor_vehicle", "vehicle", "access")
CAR_ROUTABLE = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
    "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "service",
}


def effective_access(tags: Mapping[str, str]) -> Optional[str]:
    """Motor-car access value as car.lua resolves it (most specific key first)."""

    for key in ACCESS_KEYS:
        value = tags.get(key)
        if value:
            return value.split(";")[0].strip()
    return None


def _node(lon: float, lat: float) -> int:
    return (round(lon * 1e6) + 180_000_000) << 29 | (round(lat * 1e6) + 90_000_000)


def segment_hash(a: Sequence[float], b: Sequence[float]) -> int:
    """Direction-independent 64-bit hash of a segment between two [lon, lat] points."""

    x, y = sorted((_node(a[0], a[1]), _node(b[0], b[1])))
    return int.from_bytes(hashlib.blake2b(f"{x}:{y}".encode(), digest_size=8).digest(), "big")


@dataclass
class AccessRestrictedSegments:
    hashes: array  # sorted, unique uint64
    meta: Dict[str, object]

    def __contains__(self, h: int) -> bool:
        i = bisect_left(self.hashes, h)
        return i < len(self.hashes) and self.hashes[i] == h

    def flags(self, coords: Sequence[Sequence[float]]) -> List[bool]:
        return [segment_hash(a, b) in self for a, b in zip(coords, coords[1:])]

    def through_m(self, coords: Sequence[Sequence[float]]) -> float:
        """Length on restricted segments other than a stretch touching the trip's start or end."""

        flags = self.flags(coords)
        start = 0
        while start < len(flags) and flags[start]:
            start += 1
        end = len(flags)
        while end > start and flags[end - 1]:
            end -= 1
        return sum(haversine_m(coords[i], coords[i + 1]) for i in range(start, end) if flags[i])

    @property
    def description(self) -> str:
        return (f"{self.meta.get('ways', '?')} OSM ways with motor-car access "
                f"{'/'.join(sorted(RESTRICTED_VALUES))}; {self.meta.get('source', '')}")


@lru_cache(maxsize=1)
def access_restrictions() -> Optional[AccessRestrictedSegments]:
    if not DATA_FILE.exists():
        return None
    hashes = array("Q")
    hashes.frombytes(DATA_FILE.read_bytes())
    meta = json.loads(META_FILE.read_text(encoding="utf-8")) if META_FILE.exists() else {}
    return AccessRestrictedSegments(hashes=hashes, meta=meta)


def build(pbf: str) -> Dict[str, object]:
    """Write the segment hashes and a metadata summary from an OSM PBF (needs pyosmium)."""

    import osmium

    seen = set()
    ways = 0
    by_value: Dict[str, int] = {}
    by_highway: Dict[str, int] = {}

    class Handler(osmium.SimpleHandler):
        def way(self, w):
            nonlocal ways
            highway = w.tags.get("highway")
            if highway not in CAR_ROUTABLE:
                return
            value = effective_access(w.tags)
            if value not in RESTRICTED_VALUES:
                return
            coords = [(n.location.lon, n.location.lat) for n in w.nodes if n.location.valid()]
            if len(coords) < 2:
                return
            ways += 1
            by_value[value] = by_value.get(value, 0) + 1
            by_highway[highway] = by_highway.get(highway, 0) + 1
            for a, b in zip(coords, coords[1:]):
                seen.add(segment_hash(a, b))

    Handler().apply_file(pbf, locations=True)
    hashes = array("Q", sorted(seen))
    DATA_FILE.write_bytes(hashes.tobytes())
    meta = {
        "source": f"OpenStreetMap contributors (ODbL), extracted from {Path(pbf).name}",
        "ways": ways,
        "segments": len(hashes),
        "values": sorted(RESTRICTED_VALUES),
        "ways_by_access": dict(sorted(by_value.items())),
        "ways_by_highway": dict(sorted(by_highway.items())),
        "access_keys_in_order": list(ACCESS_KEYS),
    }
    META_FILE.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta
