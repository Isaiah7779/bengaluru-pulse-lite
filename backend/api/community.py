"""Community route submissions and verified shortcuts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import current_user, settings_dep
from community.service import REQUIRED_CONFIRMATIONS, CommunityService, TracePoint
from core.errors import AppError, NotFound
from core.settings import Settings
from db.models import RouteSubmission, ShortcutCandidate, User
from db.session import get_db
from routing.schemas import VehicleMode

router = APIRouter(prefix="/v1/community", tags=["community"])


class PointIn(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    t: datetime
    accuracy_m: Optional[float] = Field(None, ge=0, le=5000)


class SubmissionIn(BaseModel):
    vehicle: VehicleMode
    points: List[PointIn] = Field(..., min_length=2, max_length=5000)
    note: Optional[str] = Field(None, max_length=500)


def submission_dict(s: RouteSubmission, include_trace: bool = False) -> dict:
    data = {
        "id": s.id, "vehicle": s.vehicle, "status": s.status, "rejection_reason": s.rejection_reason,
        "checks": s.checks, "matched_distance_m": s.matched_distance_m, "observed_duration_s": s.observed_duration_s,
        "match_confidence": s.match_confidence, "candidate_id": s.candidate_id,
        "submitted_at": s.submitted_at.isoformat() if s.submitted_at else None, "note": s.note,
        "matched_geometry": s.matched_geometry,
    }
    if include_trace:
        data["trace"] = s.trace
    return data


def candidate_dict(c: ShortcutCandidate) -> dict:
    return {
        "id": c.id, "vehicle": c.vehicle, "state": c.state, "classification": c.classification,
        "confirmations": c.confirmations, "required_confirmations": REQUIRED_CONFIRMATIONS,
        "distance_m": c.distance_m, "median_observed_duration_s": c.median_duration_s,
        "reference_distance_m": c.reference_distance_m, "reference_duration_s": c.reference_duration_s,
        "origin": {"lat": c.origin_lat, "lon": c.origin_lon},
        "destination": {"lat": c.destination_lat, "lon": c.destination_lon},
        "geometry": c.geometry, "checks": c.checks, "review_note": c.review_note,
        "last_confirmed_at": c.last_confirmed_at.isoformat() if c.last_confirmed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.post("/submissions", status_code=201)
async def submit(
    body: SubmissionIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    since = datetime.now(timezone.utc) - timedelta(days=1)
    today = db.scalar(select(func.count(RouteSubmission.id)).where(RouteSubmission.user_id == user.id, RouteSubmission.submitted_at >= since))
    if today and today >= 20:
        raise AppError("Submission limit reached (20 per day)", code="rate_limited", status_code=429)
    points = [
        TracePoint(p.lat, p.lon, p.t if p.t.tzinfo else p.t.replace(tzinfo=timezone.utc), p.accuracy_m)
        for p in body.points
    ]
    submission = await CommunityService(settings).submit(db, user.id, body.vehicle.value, points, body.note)
    db.commit()
    result = submission_dict(submission)
    if submission.candidate_id:
        result["candidate"] = candidate_dict(db.get(ShortcutCandidate, submission.candidate_id))
    return result


@router.get("/submissions/mine")
def my_submissions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(RouteSubmission).where(RouteSubmission.user_id == user.id).order_by(RouteSubmission.id.desc())).all()
    return {"submissions": [submission_dict(s) for s in rows]}


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.scalar(select(RouteSubmission).where(RouteSubmission.id == submission_id, RouteSubmission.user_id == user.id))
    if s is None:
        raise NotFound("Submission not found")
    return submission_dict(s, include_trace=True)


@router.get("/shortcuts")
def verified_shortcuts(
    vehicle: Optional[VehicleMode] = None,
    min_lat: Optional[float] = None, min_lon: Optional[float] = None,
    max_lat: Optional[float] = None, max_lon: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """Publicly visible: only admin-verified shortcuts/longcuts."""

    stmt = select(ShortcutCandidate).where(ShortcutCandidate.state == "verified")
    if vehicle:
        stmt = stmt.where(ShortcutCandidate.vehicle == vehicle.value)
    if None not in (min_lat, min_lon, max_lat, max_lon):
        stmt = stmt.where(ShortcutCandidate.origin_lat.between(min_lat, max_lat), ShortcutCandidate.origin_lon.between(min_lon, max_lon))
    rows = db.scalars(stmt.limit(500)).all()
    return {"shortcuts": [candidate_dict(c) for c in rows]}
