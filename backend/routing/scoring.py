"""Route scoring per preference, plus evidence-based explanations.

Scores are only computed for routes whose travel time is on the common
comparison basis ("comparable"); others are listed but not ranked against
them. Lower score = better.

Balanced weights are a transparent product choice (documented in ROUTING.md),
not a learned model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from routing.schemas import RoutePreference

BALANCED_WEIGHTS = {"time": 0.60, "distance": 0.20, "delay": 0.10, "incidents": 0.10}
SEVERE_INCIDENT_PENALTY = 0.5
OTHER_INCIDENT_PENALTY = 0.1

BASIS_LABEL = {
    "traffic_live": "TomTom live traffic",
    "traffic_predicted": "TomTom predicted traffic for the departure time",
    "free_flow": "OSRM free-flow estimate",
}


@dataclass
class RouteMetrics:
    eta_s: float
    distance_m: float
    delay_s: Optional[float]
    severe_incidents: int
    other_incidents: int
    comparable: bool


def resolve_preference(requested: RoutePreference, *, traffic_basis: bool, future: bool) -> Tuple[RoutePreference, Optional[str]]:
    P = RoutePreference
    if requested in (P.LEAST_TRAFFIC_NOW, P.LEAST_TRAFFIC_PREDICTED) and not traffic_basis:
        return P.FASTEST, "Traffic data unavailable for this request; ranked by fastest free-flow time instead."
    if requested == P.LEAST_TRAFFIC_NOW and future:
        return P.LEAST_TRAFFIC_PREDICTED, (
            "Departure is in the future, so current traffic does not apply; ranked by predicted traffic delay."
        )
    if requested == P.LEAST_TRAFFIC_PREDICTED and not future:
        return P.LEAST_TRAFFIC_NOW, "Departure is now; predicted traffic equals current conditions."
    return requested, None


def score_routes(pref: RoutePreference, metrics: List[RouteMetrics]) -> List[Tuple[Optional[float], Dict[str, float]]]:
    comparable = [m for m in metrics if m.comparable]
    if not comparable:
        return [(None, {}) for _ in metrics]
    best_eta = min(m.eta_s for m in comparable)
    best_dist = min(m.distance_m for m in comparable)
    out: List[Tuple[Optional[float], Dict[str, float]]] = []
    for m in metrics:
        if not m.comparable:
            out.append((None, {}))
            continue
        if pref == RoutePreference.FASTEST:
            out.append((round(m.eta_s / 60, 3), {"eta_min": round(m.eta_s / 60, 2)}))
        elif pref == RoutePreference.SHORTEST:
            out.append((round(m.distance_m / 1000, 3), {"distance_km": round(m.distance_m / 1000, 3)}))
        elif pref in (RoutePreference.LEAST_TRAFFIC_NOW, RoutePreference.LEAST_TRAFFIC_PREDICTED):
            if m.delay_s is None:
                out.append((None, {}))
            else:
                delay_min = m.delay_s / 60
                out.append((round(delay_min + 0.01 * m.eta_s / 60, 3), {"delay_min": round(delay_min, 2), "eta_min": round(m.eta_s / 60, 2)}))
        else:  # balanced
            components = {
                "time": m.eta_s / best_eta - 1,
                "distance": m.distance_m / best_dist - 1,
                "delay": (m.delay_s or 0.0) / m.eta_s,
                "incidents": min(1.0, SEVERE_INCIDENT_PENALTY * m.severe_incidents + OTHER_INCIDENT_PENALTY * m.other_incidents),
            }
            score = sum(BALANCED_WEIGHTS[k] * v for k, v in components.items())
            out.append((round(score, 4), {k: round(v, 4) for k, v in components.items()}))
    return out


def _min(seconds: float) -> str:
    return f"{seconds / 60:.1f} min"


def explain(opt, cand, options, pref: RoutePreference, basis: str) -> List[str]:
    lines: List[str] = []
    comparable = [o for o in options if o.comparable]
    if opt.recommended:
        lines.append(_recommend_reason(opt, comparable, pref, basis))
    eta_line = f"ETA {_min(opt.eta_s)} ({BASIS_LABEL.get(opt.eta_basis, opt.eta_basis)}), {opt.distance_m / 1000:.1f} km."
    lines.append(eta_line)
    if opt.traffic:
        t = opt.traffic
        lines.append(
            f"TomTom reports {_min(t.traffic_delay_s)} of traffic delay on this route"
            + (f"; free-flow would be {_min(t.no_traffic_s)}" if t.no_traffic_s else "")
            + (f"; typical for this time {_min(t.historic_s)}" if t.historic_s else "")
            + f" (route geometry matched {t.length_match_pct:.0f}%)."
        )
    if opt.traffic_note and not opt.traffic:
        lines.append(opt.traffic_note)
    if not opt.comparable:
        lines.append("Not ranked against traffic-timed routes because it has no traffic timing.")
    cls = opt.classification
    if not opt.is_reference:
        lines.append(f"{cls['type'].capitalize()}: {cls['reason']}.")
    else:
        lines.append("This is the reference route used for shortcut/longcut comparison.")
    if opt.incidents:
        severe = [i for i in opt.incidents if (i.severity or 0) >= 3 or i.category == "road_closed"]
        sample = opt.incidents[0]
        lines.append(
            f"{len(opt.incidents)} active incident(s) on this route"
            + (f", {len(severe)} major/closure" if severe else "")
            + f" — e.g. {sample.category.replace('_', ' ')}"
            + (f" on {sample.road}" if sample.road else "")
            + f" ({sample.source})."
        )
    observed = [s for s in opt.monitored_segments if s.congestion]
    for seg in sorted(observed, key=lambda s: s.speed_ratio or 1)[:3]:
        lines.append(
            f"Monitored point '{seg.name}': {seg.congestion.lower()} ({seg.current_speed_kmph:.0f} km/h, "
            f"{(seg.speed_ratio or 0) * 100:.0f}% of free-flow) observed {seg.age_minutes:.0f} min ago."
        )
    for seg in [s for s in opt.monitored_segments if s.forecast][:2]:
        f = seg.forecast
        lines.append(
            f"Pulse forecast for '{seg.name}' at departure: {f.get('predicted_speed_ratio', 0) * 100:.0f}% of free-flow "
            f"(model {f.get('model')}, test MAE {f.get('test_mae')})."
        )
    return lines


def _recommend_reason(opt, comparable, pref: RoutePreference, basis: str) -> str:
    n = len(comparable)
    label = BASIS_LABEL.get(basis, basis)
    if pref == RoutePreference.FASTEST:
        runner = sorted((o for o in comparable if o.id != opt.id), key=lambda o: o.eta_s)
        margin = f", {_min(runner[0].eta_s - opt.eta_s)} ahead of the next" if runner else ""
        return f"Recommended: fastest of {n} comparable route(s) on {label}{margin}."
    if pref == RoutePreference.SHORTEST:
        return f"Recommended: shortest of {n} route(s) ({opt.distance_m / 1000:.2f} km)."
    if pref in (RoutePreference.LEAST_TRAFFIC_NOW, RoutePreference.LEAST_TRAFFIC_PREDICTED):
        delay = opt.traffic.traffic_delay_s if opt.traffic else 0
        return f"Recommended: least traffic delay ({_min(delay)}) of {n} route(s) on {label}."
    return (
        f"Recommended: best balance of time, distance, traffic delay and incidents across {n} route(s) "
        f"(weights time {BALANCED_WEIGHTS['time']:.0%}, distance {BALANCED_WEIGHTS['distance']:.0%}, "
        f"delay {BALANCED_WEIGHTS['delay']:.0%}, incidents {BALANCED_WEIGHTS['incidents']:.0%})."
    )


def recommendation_text(best, pref: RoutePreference, basis: str, n: int) -> str:
    return best.explanation[0] if best.explanation and best.explanation[0].startswith("Recommended") else (
        f"Route {best.id} ranked first for '{pref.value}' using {BASIS_LABEL.get(basis, basis)}."
    )
