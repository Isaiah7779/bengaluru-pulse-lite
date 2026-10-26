"""Shortcut / longcut classification against an explicit reference route.

Definitions (project specification):

    SHORTCUT : shorter distance AND shorter travel time than the reference
    LONGCUT  : longer distance  AND shorter travel time than the reference
    otherwise: ALTERNATIVE

"Shorter/longer/faster" require a difference larger than a small significance
threshold so that measurement noise (a few metres or seconds) never creates a
label. Differences within the threshold count as *equal*. Travel times must be
on the same basis (both traffic-aware or both free-flow); otherwise, or if any
metric is missing, the route is UNCLASSIFIED with the reason stated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

DISTANCE_ABS_M = 50.0
DISTANCE_REL = 0.01
TIME_ABS_S = 30.0
TIME_REL = 0.02


@dataclass
class Classification:
    type: str  # reference | shortcut | longcut | alternative | unclassified
    basis: Optional[str]
    distance_diff_m: Optional[float]
    distance_diff_pct: Optional[float]
    time_diff_s: Optional[float]
    time_diff_pct: Optional[float]
    distance_relation: Optional[str]  # shorter | longer | equal
    time_relation: Optional[str]  # faster | slower | equal
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _relation(value: float, reference: float, abs_tol: float, rel_tol: float, lower: str, higher: str) -> str:
    diff = value - reference
    if abs(diff) <= max(abs_tol, rel_tol * reference):
        return "equal"
    return lower if diff < 0 else higher


def _valid(x: Optional[float]) -> bool:
    return x is not None and x == x and x > 0  # excludes None, NaN, <= 0


def classify(
    distance_m: Optional[float],
    time_s: Optional[float],
    reference_distance_m: Optional[float],
    reference_time_s: Optional[float],
    *,
    basis: Optional[str],
    reference_basis: Optional[str] = None,
    is_reference: bool = False,
) -> Classification:
    if is_reference:
        return Classification("reference", basis, 0.0, 0.0, 0.0, 0.0, "equal", "equal", "Reference route for comparison")

    if not all(_valid(v) for v in (distance_m, time_s, reference_distance_m, reference_time_s)):
        return Classification(
            "unclassified", basis, None, None, None, None, None, None,
            "Missing or invalid distance/time for this route or the reference",
        )
    if reference_basis is not None and basis != reference_basis:
        return Classification(
            "unclassified", basis, None, None, None, None, None, None,
            f"Travel times not comparable ({basis} vs reference {reference_basis})",
        )

    d_diff = distance_m - reference_distance_m
    t_diff = time_s - reference_time_s
    d_rel = _relation(distance_m, reference_distance_m, DISTANCE_ABS_M, DISTANCE_REL, "shorter", "longer")
    t_rel = _relation(time_s, reference_time_s, TIME_ABS_S, TIME_REL, "faster", "slower")
    d_pct = 100.0 * d_diff / reference_distance_m
    t_pct = 100.0 * t_diff / reference_time_s

    def fmt_d() -> str:
        return f"{abs(d_diff) / 1000:.2f} km ({abs(d_pct):.1f}%)"

    def fmt_t() -> str:
        return f"{abs(t_diff) / 60:.1f} min ({abs(t_pct):.1f}%)"

    if d_rel == "shorter" and t_rel == "faster":
        kind, reason = "shortcut", f"{fmt_d()} shorter and {fmt_t()} faster than the reference"
    elif d_rel == "longer" and t_rel == "faster":
        kind, reason = "longcut", f"{fmt_d()} longer but {fmt_t()} faster than the reference"
    else:
        parts = []
        parts.append("same distance" if d_rel == "equal" else f"{fmt_d()} {d_rel}")
        parts.append("same travel time" if t_rel == "equal" else f"{fmt_t()} {t_rel}")
        kind, reason = "alternative", " and ".join(parts) + " than the reference"

    return Classification(
        kind, basis, round(d_diff, 1), round(d_pct, 2), round(t_diff, 1), round(t_pct, 2), d_rel, t_rel,
        reason + f" ({basis} travel times)",
    )
