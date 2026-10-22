"""Bengaluru Pulse routing engine (V2).

Pipeline for one request:

1. Resolve the vehicle to the OSRM server built for that mode (no silent fallback).
2. Reference route = OSRM's primary route (free-flow fastest for the mode).
3. Candidates = OSRM native alternatives + corridor routes through lateral
   waypoints (requested in parallel), snapped by OSRM to real roads.
4. Filter impractical candidates (excessive detour, U-turn spurs) and remove
   geometric duplicates (symmetric overlap similarity).
5. Traffic timing (car / motorcycle): TomTom times each candidate's own geometry
   (supportingPoints) for the requested departure. Results whose length differs
   from OSRM by more than 8% are rejected as mismatched reconstructions.
6. Evidence: active incidents near each route, monitored-segment observations
   and (if an evaluated model is active) forecasts; weather at departure.
7. Rank by the requested preference on one comparison basis; classify each
   route against the reference (shortcut / longcut / alternative); explain.

Every number in the response comes from OSRM, TomTom, Open-Meteo, collected
observations or an evaluated model. Missing sources are reported, not filled.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select

from core.errors import AppError, UpstreamUnavailable
from core.settings import Settings
from db.models import Incident, TrafficObservation, TrafficSegment
from db.session import session_scope
from providers.tomtom import ProviderError, ProviderUnavailable, RouteTiming, TomTomProvider
from routing import scoring
from routing.classification import classify
from routing.geometry import PointIndex, backtrack_length_m, haversine_m, resample, route_similarity
from routing.osrm_client import OSRMClient, OSRMError, OSRMNoRoute, extract_route_steps
from routing.route_profiles import VehicleProfile, get_profile, get_vehicle_metadata, server_url
from routing.schemas import (
    DataSourceStatus,
    RouteIncident,
    RouteOption,
    RoutePreference,
    RouteRequestV2,
    RouteResponseV2,
    RouteSegmentEvidence,
    RouteStep,
    TrafficTiming,
)
from traffic.state_engine import congestion_level
from weather.service import WeatherService, advisories

logger = logging.getLogger(__name__)

LENGTH_MATCH_TOLERANCE = 0.08
FUTURE_THRESHOLD = timedelta(minutes=15)
MAX_DEPART_AHEAD = timedelta(days=7)
DUPLICATE_SIMILARITY = 0.85
MAX_BACKTRACK_M = 120.0
INCIDENT_RADIUS_M = 60.0
SEGMENT_RADIUS_M = 120.0
# Incident types that matter to pedestrians/cyclists (traffic jams do not).
NON_MOTOR_INCIDENTS = {"road_closed", "flooding", "road_works", "dangerous_conditions", "accident"}

ForecastLookup = Callable[[int, datetime], Optional[Dict[str, Any]]]

_TIMING_CACHE: Dict[str, Tuple[float, RouteTiming]] = {}
_TIMING_TTL_S = 300.0


@dataclass
class Candidate:
    raw: Dict[str, Any]
    origin_kind: str
    coords: List[List[float]]
    distance_m: float
    duration_s: float
    traffic: Optional[TrafficTiming] = None
    traffic_note: Optional[str] = None
    incidents: List[RouteIncident] = field(default_factory=list)
    segments: List[RouteSegmentEvidence] = field(default_factory=list)

    @property
    def is_reference(self) -> bool:
        return self.origin_kind == "osrm_primary"


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def corridor_waypoints(o_lat: float, o_lon: float, d_lat: float, d_lon: float) -> List[List[Tuple[float, float]]]:
    """Lateral via-points either side of the straight line, scaled to trip length."""

    span_m = haversine_m((o_lon, o_lat), (d_lon, d_lat))
    if span_m < 400:
        return []
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians((o_lat + d_lat) / 2))
    dx = (d_lon - o_lon) * m_per_deg_lon
    dy = (d_lat - o_lat) * m_per_deg_lat
    length = math.hypot(dx, dy)
    px, py = -dy / length, dx / length  # unit perpendicular (metres)

    def point(fraction: float, offset_m: float) -> Tuple[float, float]:
        x = dx * fraction + px * offset_m
        y = dy * fraction + py * offset_m
        return (o_lat + y / m_per_deg_lat, o_lon + x / m_per_deg_lon)

    corridors: List[List[Tuple[float, float]]] = []
    for factor in (0.07, 0.14, 0.24, 0.34):
        offset = min(max(factor * span_m, 300.0), 7_000.0)
        for side in (1, -1):
            corridors.append([point(0.3, side * offset), point(0.7, side * offset)])
    for side in (1, -1):
        corridors.append([point(0.5, side * min(max(0.18 * span_m, 300.0), 6_000.0))])
    return corridors


def clean_steps(raw_steps: List[Dict[str, Any]]) -> List[RouteStep]:
    """Drop intermediate arrive/depart steps created at corridor via-points."""

    steps: List[RouteStep] = []
    last = len(raw_steps) - 1
    for i, step in enumerate(raw_steps):
        kind = step.get("maneuver_type")
        if kind == "arrive" and i != last:
            continue
        if kind == "depart" and i != 0:
            continue
        steps.append(
            RouteStep(
                name=step.get("name") or "",
                distance_m=step.get("distance_m", 0.0),
                duration_s=step.get("duration_s", 0.0),
                instruction=step.get("instruction"),
            )
        )
    return steps


def route_summary(raw: Dict[str, Any]) -> str:
    names: List[str] = []
    weights: Dict[str, float] = {}
    for leg in raw.get("legs") or []:
        for step in leg.get("steps") or []:
            name = step.get("name") or step.get("ref")
            if name:
                weights[name] = weights.get(name, 0.0) + float(step.get("distance") or 0)
                if name not in names:
                    names.append(name)
    major = [n for n in names if weights.get(n, 0) >= 500] or names
    return ", ".join(major[:4])


class RoutingEngine:
    def __init__(
        self,
        settings: Settings,
        tomtom: Optional[TomTomProvider] = None,
        weather: Optional[WeatherService] = None,
        forecast_lookup: Optional[ForecastLookup] = None,
        clients: Optional[Dict[str, OSRMClient]] = None,
        use_database: bool = True,
    ) -> None:
        self.settings = settings
        self.tomtom = tomtom if tomtom is not None else TomTomProvider(settings)
        self.weather = weather if weather is not None else WeatherService(settings)
        self.forecast_lookup = forecast_lookup
        self.use_database = use_database
        self._clients = clients or {}

    # ------------------------------------------------------------------
    def client_for(self, profile: VehicleProfile) -> OSRMClient:
        url = server_url(self.settings, profile.vehicle)
        if not url:
            raise UpstreamUnavailable(
                f"{profile.vehicle} routing is not available: no OSRM server built with "
                f"{profile.lua_profile} is configured. Car routes are never substituted.",
                code="mode_unavailable",
            )
        if profile.osrm_profile not in self._clients:
            self._clients[profile.osrm_profile] = OSRMClient(url, timeout=self.settings.osrm_timeout_seconds)
        return self._clients[profile.osrm_profile]

    # ------------------------------------------------------------------
    async def plan(self, req: RouteRequestV2) -> RouteResponseV2:
        profile = get_profile(req.vehicle)
        now = datetime.now(timezone.utc)
        depart_at = _aware(req.depart_at) or now
        if depart_at < now - timedelta(minutes=5):
            raise AppError("Departure time is in the past", code="invalid_departure")
        if depart_at > now + MAX_DEPART_AHEAD:
            raise AppError("Departure time must be within 7 days", code="invalid_departure")
        future = depart_at - now > FUTURE_THRESHOLD
        avoid = [a.value for a in req.avoid]
        unsupported = [a for a in avoid if a not in profile.excludable]
        if unsupported:
            raise AppError(
                f"Avoid option(s) {unsupported} not supported for {profile.vehicle} "
                f"(supported: {list(profile.excludable) or 'none'})",
                code="unsupported_avoid",
            )
        if haversine_m((req.origin.lon, req.origin.lat), (req.destination.lon, req.destination.lat)) < 30:
            raise AppError("Origin and destination are the same place", code="same_place")

        client = self.client_for(profile)
        warnings: List[str] = []
        sources: List[DataSourceStatus] = []

        # 1-2. reference + native alternatives --------------------------------
        o = (req.origin.lat, req.origin.lon)
        d = (req.destination.lat, req.destination.lon)
        try:
            primary = await client.route_points([o, d], profile=profile.osrm_profile, alternatives=3, exclude=avoid)
        except OSRMNoRoute as exc:
            raise AppError(
                f"No {profile.vehicle} route found between these points ({exc}). "
                "One of them may be outside the Bengaluru road network.",
                code="no_route",
                status_code=422,
            ) from exc
        except OSRMError as exc:
            raise UpstreamUnavailable(str(exc), code="routing_engine_unavailable") from exc
        sources.append(DataSourceStatus(name="osrm", status="ok", detail=f"{profile.lua_profile} graph", as_of=now))

        snap = [float(w.get("distance") or 0) for w in primary.get("waypoints", [])]
        if any(s > 500 for s in snap):
            warnings.append(
                f"Origin/destination snapped {max(snap):.0f} m to the nearest {profile.vehicle}-accessible road."
            )

        candidates: List[Candidate] = []
        for i, raw in enumerate(primary["routes"]):
            candidates.append(self._candidate(raw, "osrm_primary" if i == 0 else "osrm_alternative"))
        reference = candidates[0]

        # 3. corridor candidates in parallel ----------------------------------
        corridors = corridor_waypoints(o[0], o[1], d[0], d[1])
        semaphore = asyncio.Semaphore(5)

        async def fetch(via):
            async with semaphore:
                try:
                    payload = await client.route_points([o, *via, d], profile=profile.osrm_profile, exclude=avoid)
                    return payload["routes"][0]
                except OSRMError:
                    return None

        for raw in await asyncio.gather(*(fetch(c) for c in corridors)):
            if raw:
                candidates.append(self._candidate(raw, "corridor"))
        considered = len(candidates)

        # 4. filter + dedup -----------------------------------------------------
        kept = self._filter_and_dedup(candidates, reference, req.max_routes)

        # 5. traffic timing -----------------------------------------------------
        traffic_status = await self._apply_traffic(kept, profile, depart_at if future else None)
        sources.append(traffic_status)

        # 6. evidence -----------------------------------------------------------
        if self.use_database:
            try:
                inc_status = self._attach_incidents(kept, motor=profile.tomtom_travel_mode is not None)
                sources.append(inc_status)
                sources.append(self._attach_segments(kept, depart_at))
            except Exception:
                logger.exception("Evidence lookup failed")
                sources.append(DataSourceStatus(name="observations_db", status="unavailable", detail="database error"))
        weather = None
        try:
            weather = await self.weather.at(o[0], o[1], depart_at)
        except Exception:
            logger.exception("Weather lookup failed")
        sources.append(
            DataSourceStatus(
                name="weather",
                status="ok" if weather else "unavailable",
                detail=(weather or {}).get("source", "Open-Meteo unreachable"),
                as_of=datetime.fromisoformat(weather["time"]) if weather else None,
            )
        )
        warnings.extend(advisories(weather, profile.vehicle))
        sources.append(
            DataSourceStatus(
                name="pulse_forecast",
                status="ok" if self.forecast_lookup else "unavailable",
                detail="evaluated model active" if self.forecast_lookup else
                "no forecasting model has passed evaluation; predictions come only from the provider",
            )
        )

        # 7. rank, classify, explain ----------------------------------------------
        return self._assemble(
            req, profile, kept, reference, depart_at, future, weather, sources, warnings, considered
        )

    # ------------------------------------------------------------------
    def _candidate(self, raw: Dict[str, Any], kind: str) -> Candidate:
        coords = (raw.get("geometry") or {}).get("coordinates") or []
        return Candidate(
            raw=raw,
            origin_kind=kind,
            coords=coords,
            distance_m=float(raw.get("distance") or 0),
            duration_s=float(raw.get("duration") or 0),
        )

    def _filter_and_dedup(self, candidates: List[Candidate], reference: Candidate, max_routes: int) -> List[Candidate]:
        ref_d, ref_t = reference.distance_m, reference.duration_s
        limit = min(max_routes, self.settings.max_route_candidates)
        kept: List[Candidate] = [reference]
        others = sorted((c for c in candidates if c is not reference), key=lambda c: c.duration_s)
        for cand in others:
            if len(kept) >= limit:
                break
            if cand.distance_m <= 0 or cand.duration_s <= 0 or len(cand.coords) < 2:
                continue
            if cand.distance_m > 1.5 * ref_d + 1000 or cand.duration_s > 1.5 * ref_t + 180:
                continue  # impractical detour
            if cand.origin_kind == "corridor" and backtrack_length_m(cand.coords) > MAX_BACKTRACK_M:
                continue  # via-point produced a U-turn spur
            if any(route_similarity(cand.coords, k.coords) >= DUPLICATE_SIMILARITY for k in kept):
                continue
            kept.append(cand)
        return kept

    # ------------------------------------------------------------------
    async def _apply_traffic(self, kept: List[Candidate], profile: VehicleProfile, future_depart: Optional[datetime]) -> DataSourceStatus:
        if profile.tomtom_travel_mode is None:
            for c in kept:
                c.traffic_note = "Road traffic is not applied to walking/cycling travel times."
            return DataSourceStatus(name="tomtom_traffic", status="not_applicable", detail=f"{profile.vehicle} mode")
        if not self.tomtom.configured:
            for c in kept:
                c.traffic_note = "No traffic provider configured; free-flow estimate only."
            return DataSourceStatus(name="tomtom_traffic", status="not_configured", detail="TOMTOM_API_KEY not set")

        to_eval = kept[: self.settings.tomtom_route_eval_max]
        basis = "traffic_predicted" if future_depart else "traffic_live"
        semaphore = asyncio.Semaphore(4)
        errors: List[str] = []

        async def evaluate(c: Candidate):
            key = hashlib.sha1(
                repr((profile.tomtom_travel_mode, [tuple(round(v, 4) for v in p) for p in c.coords[:: max(len(c.coords) // 60, 1)]],
                      future_depart.replace(second=0, microsecond=0, minute=(future_depart.minute // 5) * 5).isoformat() if future_depart else "now")).encode()
            ).hexdigest()
            hit = _TIMING_CACHE.get(key)
            if hit and hit[0] > time.monotonic():
                timing = hit[1]
            else:
                async with semaphore:
                    timing = await self.tomtom.route_timing(
                        c.coords, depart_at=future_depart, travel_mode=profile.tomtom_travel_mode
                    )
                _TIMING_CACHE[key] = (time.monotonic() + _TIMING_TTL_S, timing)
            match = abs(timing.length_m - c.distance_m) / c.distance_m
            if match > LENGTH_MATCH_TOLERANCE:
                c.traffic_note = (
                    f"TomTom timing rejected: its reconstruction differs in length by {match:.0%} "
                    "from this route, so it is not this route's travel time."
                )
                return
            c.traffic = TrafficTiming(
                source="tomtom",
                basis=basis,
                eta_s=timing.travel_time_s,
                traffic_delay_s=timing.traffic_delay_s,
                no_traffic_s=timing.no_traffic_s,
                historic_s=timing.historic_s,
                live_s=timing.live_s,
                provider_length_m=timing.length_m,
                length_match_pct=round(100 * (1 - match), 1),
                depart_at=timing.departure,
                arrive_at=timing.arrival,
            )

        results = await asyncio.gather(*(evaluate(c) for c in to_eval), return_exceptions=True)
        for c, result in zip(to_eval, results):
            if isinstance(result, ProviderUnavailable):
                c.traffic_note = f"Traffic unavailable: {result}"
                errors.append(str(result))
            elif isinstance(result, ProviderError):
                c.traffic_note = f"Traffic unavailable: {result}"
                errors.append(str(result))
            elif isinstance(result, Exception):
                logger.exception("Traffic evaluation failed", exc_info=result)
                c.traffic_note = "Traffic unavailable: internal error"
                errors.append("internal error")
        for c in kept[len(to_eval):]:
            c.traffic_note = c.traffic_note or (
                f"Not traffic-timed (only the first {len(to_eval)} candidates are timed to stay within the free API quota)."
            )
        timed = sum(1 for c in kept if c.traffic)
        if timed == 0:
            return DataSourceStatus(
                name="tomtom_traffic", status="unavailable",
                detail="; ".join(sorted(set(errors))) or "no route could be matched",
            )
        detail = f"{timed}/{len(kept)} routes timed ({'departAt prediction' if future_depart else 'live traffic'})"
        return DataSourceStatus(
            name="tomtom_traffic", status="ok" if not errors else "degraded", detail=detail,
            as_of=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    def _route_index(self, c: Candidate) -> Tuple[PointIndex, Tuple[float, float, float, float]]:
        samples = resample(c.coords, 30.0)
        lons = [p[0] for p in samples]
        lats = [p[1] for p in samples]
        return PointIndex(samples, cell_m=60.0), (min(lons), min(lats), max(lons), max(lats))

    def _attach_incidents(self, kept: List[Candidate], motor: bool = True) -> DataSourceStatus:
        margin = 0.002
        with session_scope() as session:
            last_sweep = None
            for c in kept:
                index, (min_lon, min_lat, max_lon, max_lat) = self._route_index(c)
                rows = session.scalars(
                    select(Incident).where(
                        Incident.active.is_(True),
                        Incident.status == "published",
                        Incident.lat.between(min_lat - margin, max_lat + margin),
                        Incident.lon.between(min_lon - margin, max_lon + margin),
                    )
                ).all()
                for inc in rows:
                    if not motor and inc.category not in NON_MOTOR_INCIDENTS:
                        continue
                    last_sweep = max(filter(None, [last_sweep, _aware(inc.last_seen_at)]), default=None)
                    points = [(inc.lon, inc.lat)]
                    geom = inc.geometry or {}
                    if geom.get("type") == "LineString":
                        points = [tuple(p) for p in geom.get("coordinates", [])][::3] or points
                    best = min(
                        (haversine_m(p, q) for p in points for q in index.neighbours(p[0], p[1], INCIDENT_RADIUS_M)),
                        default=math.inf,
                    )
                    if best <= INCIDENT_RADIUS_M:
                        c.incidents.append(
                            RouteIncident(
                                id=inc.id, category=inc.category, severity=inc.severity,
                                description=inc.description,
                                road=" → ".join(filter(None, [inc.road_from, inc.road_to])) or None,
                                lat=inc.lat, lon=inc.lon, distance_from_route_m=round(best, 1), source=inc.source,
                            )
                        )
            total_active = session.query(Incident).filter(Incident.active.is_(True)).count()
        if total_active == 0:
            return DataSourceStatus(name="incidents", status="unavailable", detail="no incident data collected yet")
        return DataSourceStatus(name="incidents", status="ok", detail=f"{total_active} active incidents (TomTom sweep)", as_of=last_sweep)

    def _attach_segments(self, kept: List[Candidate], depart_at: datetime) -> DataSourceStatus:
        now = datetime.now(timezone.utc)
        with session_scope() as session:
            segments = session.scalars(select(TrafficSegment).where(TrafficSegment.active.is_(True))).all()
            latest: Dict[int, TrafficObservation] = {}
            for seg in segments:
                obs = session.scalars(
                    select(TrafficObservation)
                    .where(TrafficObservation.segment_id == seg.id)
                    .order_by(TrafficObservation.observed_at.desc())
                    .limit(1)
                ).first()
                if obs:
                    latest[seg.id] = obs
            for c in kept:
                index, _ = self._route_index(c)
                for seg in segments:
                    # Probe at the monitored point snapped onto the provider segment.
                    # (TomTom segment geometries can extend several km either side.)
                    probe = (seg.lon, seg.lat)
                    if seg.geometry and seg.geometry.get("coordinates"):
                        probe = min(seg.geometry["coordinates"], key=lambda q: haversine_m(q, (seg.lon, seg.lat)))
                    near = next(index.neighbours(probe[0], probe[1], SEGMENT_RADIUS_M), None) is not None
                    if not near:
                        continue
                    obs = latest.get(seg.id)
                    observed = _aware(obs.observed_at) if obs else None
                    age = (now - observed).total_seconds() / 60 if observed else None
                    fresh = age is not None and age <= self.settings.observation_stale_minutes
                    forecast = None
                    if self.forecast_lookup:
                        try:
                            forecast = self.forecast_lookup(seg.id, depart_at)
                        except Exception:
                            logger.exception("Forecast lookup failed")
                    c.segments.append(
                        RouteSegmentEvidence(
                            segment_id=seg.id, name=seg.name,
                            congestion=congestion_level(obs.speed_ratio, obs.road_closure) if fresh else None,
                            speed_ratio=obs.speed_ratio if fresh else None,
                            current_speed_kmph=obs.current_speed_kmph if fresh else None,
                            observed_at=observed, age_minutes=round(age, 1) if age is not None else None,
                            forecast=forecast,
                        )
                    )
        fresh_count = sum(1 for obs in latest.values() if (now - _aware(obs.observed_at)).total_seconds() / 60 <= self.settings.observation_stale_minutes)
        if not latest:
            return DataSourceStatus(name="monitored_segments", status="unavailable", detail="no observations collected yet")
        return DataSourceStatus(
            name="monitored_segments", status="ok" if fresh_count else "degraded",
            detail=f"{fresh_count}/{len(segments)} monitored points fresh (sample points, not city-wide coverage)",
            as_of=max(_aware(o.observed_at) for o in latest.values()),
        )

    # ------------------------------------------------------------------
    def _assemble(self, req, profile, kept, reference, depart_at, future, weather, sources, warnings, considered) -> RouteResponseV2:
        traffic_basis = reference.traffic is not None
        basis = reference.traffic.basis if traffic_basis else "free_flow"

        def eta(c: Candidate) -> Tuple[float, str, bool]:
            if traffic_basis:
                if c.traffic:
                    return c.traffic.eta_s, c.traffic.basis, True
                return c.duration_s, "free_flow", False
            return c.duration_s, "free_flow", True

        requested = req.preference
        applied, note = scoring.resolve_preference(requested, traffic_basis=traffic_basis, future=future)
        metrics = []
        for c in kept:
            t, b, comparable = eta(c)
            metrics.append(
                scoring.RouteMetrics(
                    eta_s=t, distance_m=c.distance_m, delay_s=c.traffic.traffic_delay_s if c.traffic else None,
                    severe_incidents=sum(1 for i in c.incidents if (i.severity or 0) >= 3 or i.category == "road_closed"),
                    other_incidents=sum(1 for i in c.incidents if not ((i.severity or 0) >= 3 or i.category == "road_closed")),
                    comparable=comparable if applied != RoutePreference.SHORTEST else True,
                )
            )
        scores = scoring.score_routes(applied, metrics)
        order = sorted(range(len(kept)), key=lambda i: (scores[i][0] is None, scores[i][0] if scores[i][0] is not None else 0, metrics[i].eta_s))
        best_index = order[0]

        ref_eta, ref_basis, _ = eta(reference)
        options: List[RouteOption] = []
        for rank, i in enumerate(order, start=1):
            c = kept[i]
            t, b, comparable = eta(c)
            if c.is_reference:
                cls = classify(None, None, None, None, basis=b, is_reference=True)
            elif b == ref_basis:
                cls = classify(c.distance_m, t, reference.distance_m, ref_eta, basis=b, reference_basis=ref_basis)
            else:  # compare on free-flow for both so the basis is identical
                cls = classify(c.distance_m, c.duration_s, reference.distance_m, reference.duration_s,
                               basis="free_flow", reference_basis="free_flow")
            score, components = scores[i]
            options.append(
                RouteOption(
                    id=f"r{rank}", rank=rank, is_reference=c.is_reference, recommended=i == best_index,
                    origin_kind=c.origin_kind, distance_m=round(c.distance_m, 1),
                    free_flow_duration_s=round(c.duration_s, 1), eta_s=round(t, 1), eta_basis=b,
                    comparable=comparable, traffic=c.traffic, traffic_note=c.traffic_note,
                    classification=cls.to_dict(), score=score, score_components=components,
                    incidents=c.incidents, monitored_segments=c.segments,
                    summary=route_summary(c.raw),
                    geometry={"type": "LineString", "coordinates": c.coords},
                    steps=clean_steps(extract_route_steps(c.raw)) if req.include_steps else [],
                )
            )
        for opt, i in zip(options, order):
            opt.explanation = scoring.explain(opt, kept[i], options, applied, basis)
        best = options[0]
        reference_option = next(o for o in options if o.is_reference)
        if not traffic_basis and profile.tomtom_travel_mode:
            warnings.append(
                "Travel times are OSRM free-flow estimates; actual Bengaluru traffic is usually slower."
            )
        return RouteResponseV2(
            vehicle=req.vehicle,
            vehicle_profile=get_vehicle_metadata(profile.vehicle, self.settings),
            preference_requested=requested,
            preference_applied=applied,
            preference_note=note,
            depart_at=depart_at,
            departure_mode="future" if future else "now",
            comparison_basis=basis,
            reference_route_id=reference_option.id,
            reference_description=(
                f"OSRM's default route for {profile.vehicle} ({profile.lua_profile}), fastest under free-flow "
                "conditions; all shortcut/longcut labels are relative to it."
            ),
            recommended_route_id=best.id,
            recommendation=scoring.recommendation_text(best, applied, basis, len(options)),
            routes=options,
            weather=weather,
            data_sources=sources,
            warnings=warnings,
            candidates_considered=considered,
        )
