"""Community route submissions → validated shortcut candidates.

Lifecycle of a ShortcutCandidate:

    candidate ──(≥3 independent confirmations + consistent)──> under_review
    under_review ──admin──> verified | rejected
    candidate/under_review/verified ──(no confirmation for STALE_AFTER)──> stale
    stale ──new confirmation──> candidate (re-enters review)

Nothing is ever verified automatically. A submission is accepted only after:
  * trace sanity (point count, increasing timestamps, inside Bengaluru, duration),
  * staleness (trip ended within SUBMISSION_MAX_AGE),
  * GPS-noise filtering (accuracy, implied-speed teleport removal),
  * map matching on the vehicle's own OSRM graph (encodes access/one-way rules),
  * consistency of trace length vs matched length and plausible speeds,
  * comparison with the reference route on one comparable time basis.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.errors import AppError
from core.settings import Settings
from db.models import AuditLog, RouteSubmission, ShortcutCandidate, as_utc
from providers.tomtom import ProviderError, TomTomProvider
from routing.classification import classify
from routing.geometry import haversine_m, line_length_m, route_similarity
from routing.osrm_client import OSRMClient, OSRMError
from routing.route_profiles import get_profile, server_url

logger = logging.getLogger(__name__)

REQUIRED_CONFIRMATIONS = 3
STALE_AFTER = timedelta(days=180)
SUBMISSION_MAX_AGE = timedelta(days=7)
MAX_SPEED_KMH = {"car": 110, "motorcycle": 110, "bicycle": 45, "walk": 12}
MIN_POINTS, MAX_POINTS = 10, 5000
MIN_DURATION_S, MAX_DURATION_S = 120, 3 * 3600
MAX_ACCURACY_M = 50
ENDPOINT_RADIUS_M = 300.0
SAME_ROUTE_SIMILARITY = 0.8
BENGALURU = (12.70, 77.30, 13.30, 77.95)


@dataclass
class TracePoint:
    lat: float
    lon: float
    t: datetime
    accuracy_m: Optional[float] = None


@dataclass
class Validation:
    ok: bool
    checks: Dict[str, Any] = field(default_factory=dict)
    reason: Optional[str] = None


def _reject(checks: Dict[str, Any], key: str, reason: str) -> Validation:
    checks[key] = {"passed": False, "detail": reason}
    return Validation(False, checks, reason)


def clean_trace(points: List[TracePoint], vehicle: str, now: Optional[datetime] = None) -> Tuple[List[TracePoint], Validation]:
    now = now or datetime.now(timezone.utc)
    checks: Dict[str, Any] = {}
    if not MIN_POINTS <= len(points) <= MAX_POINTS:
        return [], _reject(checks, "point_count", f"trace needs {MIN_POINTS}-{MAX_POINTS} points (got {len(points)})")
    checks["point_count"] = {"passed": True, "detail": len(points)}
    if any(points[i + 1].t <= points[i].t for i in range(len(points) - 1)):
        return [], _reject(checks, "timestamps", "timestamps must be strictly increasing")
    if points[-1].t > now + timedelta(minutes=5):
        return [], _reject(checks, "timestamps", "trace contains future timestamps")
    checks["timestamps"] = {"passed": True}
    if now - points[-1].t > SUBMISSION_MAX_AGE:
        return [], _reject(checks, "staleness", f"trip ended more than {SUBMISSION_MAX_AGE.days} days ago")
    checks["staleness"] = {"passed": True, "trip_end": points[-1].t.isoformat()}
    if not all(BENGALURU[0] <= p.lat <= BENGALURU[2] and BENGALURU[1] <= p.lon <= BENGALURU[3] for p in points):
        return [], _reject(checks, "area", "trace leaves the Bengaluru service area")
    checks["area"] = {"passed": True}

    accurate = [p for p in points if p.accuracy_m is None or p.accuracy_m <= MAX_ACCURACY_M]
    max_speed = MAX_SPEED_KMH[vehicle] / 3.6 * 1.5  # tolerate GPS jitter
    kept = [accurate[0]] if accurate else []
    for p in accurate[1:]:
        prev = kept[-1]
        dt = (p.t - prev.t).total_seconds()
        if haversine_m((prev.lon, prev.lat), (p.lon, p.lat)) / dt <= max_speed:
            kept.append(p)
    dropped = len(points) - len(kept)
    noise = {"passed": dropped <= 0.2 * len(points), "dropped_points": dropped, "kept_points": len(kept)}
    checks["gps_noise"] = noise
    if not noise["passed"] or len(kept) < MIN_POINTS:
        return [], Validation(False, checks, f"GPS trace too noisy ({dropped} of {len(points)} points implausible)")

    duration = (kept[-1].t - kept[0].t).total_seconds()
    if not MIN_DURATION_S <= duration <= MAX_DURATION_S:
        return [], _reject(checks, "duration", f"trip duration {duration / 60:.1f} min outside 2-180 min")
    checks["duration"] = {"passed": True, "seconds": duration}
    return kept, Validation(True, checks)


def endpoint_signature(vehicle: str, start: Tuple[float, float], end: Tuple[float, float]) -> str:
    cell = lambda p: (round(p[0] / 0.003), round(p[1] / 0.003))  # ~300 m grid
    return hashlib.sha1(f"{vehicle}|{cell(start)}|{cell(end)}".encode()).hexdigest()[:32]


class CommunityService:
    def __init__(self, settings: Settings, tomtom: Optional[TomTomProvider] = None) -> None:
        self.settings = settings
        self.tomtom = tomtom if tomtom is not None else TomTomProvider(settings)

    def _client(self, vehicle: str) -> OSRMClient:
        url = server_url(self.settings, vehicle)
        if not url:
            raise AppError(f"{vehicle} routing graph not available; cannot validate this submission", code="mode_unavailable", status_code=503)
        return OSRMClient(url, timeout=15.0)

    async def _match(self, vehicle: str, points: List[TracePoint]) -> Dict[str, Any]:
        sample = points
        if len(points) > 100:  # OSRM default max matching size is 100 coordinates
            step = (len(points) - 1) / 99
            sample = [points[round(i * step)] for i in range(100)]
        profile = get_profile(vehicle)
        payload = await self._client(vehicle).match(
            [(p.lat, p.lon) for p in sample],
            timestamps=[int(p.t.timestamp()) for p in sample],
            radiuses=[min(max(p.accuracy_m or 20.0, 10.0), 50.0) for p in sample],
            profile=profile.osrm_profile,
        )
        return payload

    async def _timing_basis(self, vehicle: str, matched: List[List[float]], reference: Dict[str, Any], trip_start: datetime):
        """Comparable travel times for submitted vs reference route.

        TomTom typical traffic (same weekday and time next week) for both when
        possible; otherwise OSRM free-flow for both.
        """

        profile = get_profile(vehicle)
        if profile.tomtom_travel_mode and self.tomtom.configured:
            depart = trip_start + timedelta(days=7 * ((datetime.now(timezone.utc) - trip_start).days // 7 + 1))
            try:
                sub = await self.tomtom.route_timing(matched, depart_at=depart, travel_mode=profile.tomtom_travel_mode, purpose="community")
                ref = await self.tomtom.route_timing(reference["geometry"]["coordinates"], depart_at=depart,
                                                     travel_mode=profile.tomtom_travel_mode, purpose="community")
                sub_t = sub.historic_s or sub.travel_time_s
                ref_t = ref.historic_s or ref.travel_time_s
                return sub_t, ref_t, "tomtom_typical", {"depart_reference": depart.isoformat()}
            except ProviderError as exc:
                logger.info("TomTom basis unavailable for submission: %s", exc)
        return None, float(reference["duration"]), "free_flow", {}

    async def submit(self, db: Session, user_id: int, vehicle: str, points: List[TracePoint], note: Optional[str]) -> RouteSubmission:
        submission = RouteSubmission(
            user_id=user_id, vehicle=vehicle, note=note,
            trace=[{"lat": p.lat, "lon": p.lon, "t": p.t.isoformat(), "acc": p.accuracy_m} for p in points],
        )
        db.add(submission)
        kept, validation = clean_trace(points, vehicle)
        checks = validation.checks
        if not validation.ok:
            return self._finish(db, submission, "rejected", validation.reason, checks)

        try:
            match = await self._match(vehicle, kept)
        except OSRMError as exc:
            return self._finish(db, submission, "rejected",
                                f"trace could not be matched to legal {vehicle} roads ({exc})", checks)
        matchings = match.get("matchings") or []
        main = max(matchings, key=lambda m: m.get("distance", 0)) if matchings else None
        if main is None:
            return self._finish(db, submission, "rejected", "no map match", checks)
        confidence = float(main.get("confidence") or 0)
        trace_len = line_length_m([[p.lon, p.lat] for p in kept])
        matched_len = float(main["distance"])
        coverage = matched_len / max(sum(m.get("distance", 0) for m in matchings), 1)
        ratio = matched_len / max(trace_len, 1)
        checks["map_match"] = {
            "passed": confidence >= 0.5 and len(matchings) <= 2 and coverage >= 0.9,
            "confidence": round(confidence, 3), "matchings": len(matchings), "coverage": round(coverage, 3),
            "profile": get_profile(vehicle).lua_profile,
        }
        checks["length_consistency"] = {"passed": 0.8 <= ratio <= 1.3, "trace_m": round(trace_len), "matched_m": round(matched_len)}
        if not checks["map_match"]["passed"]:
            return self._finish(db, submission, "rejected",
                                f"trace is not consistent with legal {vehicle} roads (match confidence {confidence:.2f})", checks)
        if not checks["length_consistency"]["passed"]:
            return self._finish(db, submission, "rejected", "matched route length inconsistent with the GPS trace", checks)

        matched_coords = main["geometry"]["coordinates"]
        duration = (kept[-1].t - kept[0].t).total_seconds()
        avg_kmh = matched_len / duration * 3.6
        checks["speed"] = {"passed": avg_kmh <= MAX_SPEED_KMH[vehicle], "average_kmh": round(avg_kmh, 1)}
        if not checks["speed"]["passed"]:
            return self._finish(db, submission, "rejected", f"average speed {avg_kmh:.0f} km/h implausible for {vehicle}", checks)

        submission.matched_geometry = {"type": "LineString", "coordinates": matched_coords}
        submission.matched_distance_m = matched_len
        submission.observed_duration_s = duration
        submission.match_confidence = confidence

        start = (matched_coords[0][1], matched_coords[0][0])
        end = (matched_coords[-1][1], matched_coords[-1][0])
        try:
            ref_payload = await self._client(vehicle).route_points([start, end], profile=get_profile(vehicle).osrm_profile, steps=False)
        except OSRMError as exc:
            return self._finish(db, submission, "rejected", f"reference route unavailable ({exc})", checks)
        reference = ref_payload["routes"][0]
        sub_t, ref_t, basis, basis_info = await self._timing_basis(vehicle, matched_coords, reference, kept[0].t)
        if basis == "free_flow":
            # Free-flow time for the matched path: OSRM route through sampled matched points.
            via = matched_coords[:: max(len(matched_coords) // 20, 1)][1:-1][:20]
            try:
                via_payload = await self._client(vehicle).route_points(
                    [start, *[(c[1], c[0]) for c in via], end], profile=get_profile(vehicle).osrm_profile, steps=False
                )
                sub_t = float(via_payload["routes"][0]["duration"])
            except OSRMError:
                sub_t = None
        cls = classify(matched_len, sub_t, float(reference["distance"]), ref_t, basis=basis, reference_basis=basis)
        checks["comparison"] = {"basis": basis, **basis_info, "classification": cls.to_dict(),
                                "observed_duration_s": round(duration)}
        if sub_t:
            checks["observed_vs_estimate"] = {"passed": 0.4 <= duration / sub_t <= 3.0, "ratio": round(duration / sub_t, 2)}

        if cls.type not in ("shortcut", "longcut"):
            return self._finish(db, submission, "accepted",
                                f"valid trip, classified '{cls.type}' — no shortcut candidate created", checks)

        candidate = self._find_candidate(db, vehicle, start, end, matched_coords)
        if candidate is not None:
            already = db.scalar(
                select(RouteSubmission.id).where(
                    RouteSubmission.candidate_id == candidate.id,
                    RouteSubmission.user_id == user_id,
                    RouteSubmission.status == "accepted",
                )
            )
            if already:
                return self._finish(db, submission, "rejected",
                                    "you have already confirmed this route; confirmations must be independent", checks)
        else:
            candidate = ShortcutCandidate(
                signature=endpoint_signature(vehicle, start, end), vehicle=vehicle,
                origin_lat=start[0], origin_lon=start[1], destination_lat=end[0], destination_lon=end[1],
                geometry={"type": "LineString", "coordinates": matched_coords}, distance_m=matched_len,
                reference_distance_m=float(reference["distance"]), reference_duration_s=ref_t,
                classification=cls.type, state="candidate", confirmations=0, checks={},
            )
            db.add(candidate)
            db.flush()
        submission.candidate_id = candidate.id
        self._finish(db, submission, "accepted", None, checks)
        self.refresh_candidate(db, candidate)
        return submission

    def _find_candidate(self, db: Session, vehicle: str, start, end, coords) -> Optional[ShortcutCandidate]:
        rows = db.scalars(
            select(ShortcutCandidate).where(
                ShortcutCandidate.vehicle == vehicle, ShortcutCandidate.state != "rejected",
                ShortcutCandidate.origin_lat.between(start[0] - 0.004, start[0] + 0.004),
                ShortcutCandidate.origin_lon.between(start[1] - 0.004, start[1] + 0.004),
            )
        ).all()
        for c in rows:
            if haversine_m((c.origin_lon, c.origin_lat), (start[1], start[0])) > ENDPOINT_RADIUS_M:
                continue
            if haversine_m((c.destination_lon, c.destination_lat), (end[1], end[0])) > ENDPOINT_RADIUS_M:
                continue
            if route_similarity(c.geometry["coordinates"], coords) >= SAME_ROUTE_SIMILARITY:
                return c
        return None

    @staticmethod
    def _finish(db: Session, submission: RouteSubmission, status: str, reason: Optional[str], checks) -> RouteSubmission:
        submission.status = status
        submission.rejection_reason = reason if status == "rejected" else None
        if status != "rejected" and reason:
            checks["note"] = reason
        submission.checks = checks
        db.flush()
        return submission

    @staticmethod
    def refresh_candidate(db: Session, candidate: ShortcutCandidate) -> None:
        subs = db.scalars(
            select(RouteSubmission).where(RouteSubmission.candidate_id == candidate.id, RouteSubmission.status == "accepted")
        ).all()
        independent = {s.user_id for s in subs}
        candidate.confirmations = len(independent)
        durations = [s.observed_duration_s for s in subs if s.observed_duration_s]
        candidate.median_duration_s = statistics.median(durations) if durations else None
        kinds = [((s.checks or {}).get("comparison") or {}).get("classification", {}).get("type") for s in subs]
        agreeing = sum(1 for k in kinds if k == candidate.classification)
        consistent = agreeing >= max(2, round(0.66 * len(kinds)))
        candidate.checks = {
            "independent_users": len(independent),
            "submissions": len(subs),
            "classification_agreement": f"{agreeing}/{len(kinds)}",
            "consistent": consistent,
            "observed_durations_s": [round(d) for d in durations],
        }
        candidate.last_confirmed_at = max((as_utc(s.submitted_at) for s in subs), default=None)
        if candidate.state in ("candidate", "stale") and candidate.confirmations >= REQUIRED_CONFIRMATIONS and consistent:
            candidate.state = "under_review"
        elif candidate.state == "stale":
            candidate.state = "candidate"
        db.flush()


def decide(db: Session, candidate: ShortcutCandidate, decision: str, admin_id: int, note: Optional[str]) -> ShortcutCandidate:
    if decision == "verify":
        if candidate.state != "under_review":
            raise AppError("Only candidates under review can be verified", code="invalid_state", status_code=409)
        if candidate.confirmations < REQUIRED_CONFIRMATIONS:
            raise AppError(f"At least {REQUIRED_CONFIRMATIONS} independent confirmations are required", code="insufficient_confirmations", status_code=409)
        candidate.state = "verified"
    elif decision == "reject":
        candidate.state = "rejected"
    elif decision == "stale":
        candidate.state = "stale"
    else:
        raise AppError("decision must be verify, reject or stale", code="invalid_decision", status_code=422)
    candidate.reviewed_by = admin_id
    candidate.review_note = note
    db.add(AuditLog(actor_user_id=admin_id, action=f"shortcut.{decision}", target=f"candidate:{candidate.id}", details={"note": note}))
    db.flush()
    return candidate


def mark_stale(db: Session, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = now - STALE_AFTER
    changed = 0
    for c in db.scalars(select(ShortcutCandidate).where(ShortcutCandidate.state.in_(["candidate", "under_review", "verified"]))).all():
        last = as_utc(c.last_confirmed_at or c.created_at)
        if last < cutoff:
            c.state = "stale"
            changed += 1
    db.flush()
    return changed


def purge_old_traces(db: Session, settings: Settings, now: Optional[datetime] = None) -> int:
    """Privacy: drop raw GPS traces after the retention period (matched geometry is kept)."""

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.retention_submission_trace_days)
    rows = db.scalars(select(RouteSubmission).where(RouteSubmission.submitted_at < cutoff, RouteSubmission.trace.is_not(None))).all()
    for r in rows:
        r.trace = None
    db.flush()
    return len(rows)
