"""Geometry helpers for route comparison (pure Python, coordinates as [lon, lat])."""

from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

EARTH_RADIUS_M = 6_371_008.8
Coord = Sequence[float]  # [lon, lat]


def haversine_m(a: Coord, b: Coord) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def line_length_m(coords: Sequence[Coord]) -> float:
    return sum(haversine_m(coords[i], coords[i + 1]) for i in range(len(coords) - 1))


def resample(coords: Sequence[Coord], spacing_m: float) -> List[Tuple[float, float, float]]:
    """Points every `spacing_m` along the line as (lon, lat, distance_along_m)."""

    if not coords:
        return []
    out = [(float(coords[0][0]), float(coords[0][1]), 0.0)]
    travelled = 0.0
    next_mark = spacing_m
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        seg = haversine_m(a, b)
        while seg > 0 and travelled + seg >= next_mark:
            t = (next_mark - travelled) / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, next_mark))
            next_mark += spacing_m
        travelled += seg
    last = coords[-1]
    if out[-1][2] < travelled:
        out.append((float(last[0]), float(last[1]), travelled))
    return out


class PointIndex:
    """Uniform grid index for 'is there a point within r metres' queries."""

    def __init__(self, points: Sequence[Tuple[float, ...]], cell_m: float = 50.0) -> None:
        self.cell_deg = cell_m / 111_000.0
        self.cells: Dict[Tuple[int, int], List[Tuple[float, ...]]] = {}
        for p in points:
            self.cells.setdefault(self._key(p[0], p[1]), []).append(p)

    def _key(self, lon: float, lat: float) -> Tuple[int, int]:
        return int(math.floor(lon / self.cell_deg)), int(math.floor(lat / self.cell_deg))

    def neighbours(self, lon: float, lat: float, radius_m: float):
        reach = int(math.ceil(radius_m / 111_000.0 / self.cell_deg)) + 1
        kx, ky = self._key(lon, lat)
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for p in self.cells.get((kx + dx, ky + dy), ()):
                    if haversine_m((lon, lat), p) <= radius_m:
                        yield p


def overlap_fraction(a: Sequence[Coord], b: Sequence[Coord], tolerance_m: float = 40.0, spacing_m: float = 50.0) -> float:
    """Fraction of route `a` (by length) lying within `tolerance_m` of route `b`."""

    sa = resample(a, spacing_m)
    sb = resample(b, spacing_m / 2)
    if len(sa) < 2 or not sb:
        return 0.0
    index = PointIndex(sb)
    near = sum(1 for p in sa if next(index.neighbours(p[0], p[1], tolerance_m), None) is not None)
    return near / len(sa)


def route_similarity(a: Sequence[Coord], b: Sequence[Coord], tolerance_m: float = 40.0) -> float:
    """Symmetric geometric similarity in [0, 1] (min of both directional overlaps)."""

    return min(overlap_fraction(a, b, tolerance_m), overlap_fraction(b, a, tolerance_m))


def backtrack_length_m(coords: Sequence[Coord], tolerance_m: float = 15.0, spacing_m: float = 25.0, min_gap_m: float = 200.0) -> float:
    """Length of the route that retraces road it already used (U-turn spurs).

    A point counts as retraced if it lies within `tolerance_m` of a point that is
    at least `min_gap_m` earlier along the route.
    """

    samples = resample(coords, spacing_m)
    index = PointIndex(samples, cell_m=25.0)
    retraced = 0
    for p in samples:
        for q in index.neighbours(p[0], p[1], tolerance_m):
            if p[2] - q[2] >= min_gap_m:
                retraced += 1
                break
    return retraced * spacing_m


def min_distance_to_route_m(point: Coord, route_samples_index: PointIndex, max_radius_m: float) -> float:
    best = math.inf
    for q in route_samples_index.neighbours(point[0], point[1], max_radius_m):
        best = min(best, haversine_m(point, q))
    return best
