"""Administrator endpoints. Every route depends on require_admin (role read from DB)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.community import candidate_dict, submission_dict
from api.deps import require_admin, settings_dep
from api.health import dependency_report
from api.traffic_api import incident_dict
from community.service import decide, mark_stale
from core.errors import AppError, NotFound
from core.settings import Settings
from db.models import (
    AuditLog,
    EvaluationRecord,
    Incident,
    ModelVersion,
    RouteSubmission,
    ShortcutCandidate,
    Trip,
    User,
)
from db.session import get_db
from traffic.state_engine import freshness_report

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


def user_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role, "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
    }


@router.get("/users")
def list_users(
    q: Optional[str] = Query(None, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(User).order_by(User.id)
    if q:
        stmt = stmt.where(User.email.contains(q.lower()) | User.display_name.contains(q))
    return {"users": [user_dict(u) for u in db.scalars(stmt.limit(limit)).all()],
            "total": db.scalar(select(func.count(User.id)))}


class UserUpdate(BaseModel):
    role: Optional[Literal["user", "admin"]] = None
    is_active: Optional[bool] = None


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("User not found")
    if target.id == admin.id and (body.role is not None or body.is_active is not None):
        raise AppError("Administrators cannot change their own role or status", code="self_modification", status_code=409)
    removing_admin = target.role == "admin" and (body.role == "user" or body.is_active is False)
    if removing_admin:
        active_admins = db.scalar(select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True)))
        if active_admins <= 1:
            raise AppError("Cannot remove the last active administrator", code="last_admin", status_code=409)
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(target, key, value)
    db.add(AuditLog(actor_user_id=admin.id, action="admin.user_update", target=f"user:{target.id}", details=changes))
    db.commit()
    return user_dict(target)


@router.get("/community/candidates")
def candidates(state: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(ShortcutCandidate).order_by(ShortcutCandidate.updated_at.desc())
    if state:
        stmt = stmt.where(ShortcutCandidate.state == state)
    return {"candidates": [candidate_dict(c) for c in db.scalars(stmt.limit(500)).all()]}


@router.get("/community/candidates/{candidate_id}")
def candidate_detail(candidate_id: int, db: Session = Depends(get_db)):
    c = db.get(ShortcutCandidate, candidate_id)
    if c is None:
        raise NotFound("Candidate not found")
    subs = db.scalars(select(RouteSubmission).where(RouteSubmission.candidate_id == c.id)).all()
    return {**candidate_dict(c), "submissions": [submission_dict(s) for s in subs]}


class Decision(BaseModel):
    decision: Literal["verify", "reject", "stale"]
    note: Optional[str] = Field(None, max_length=1000)


@router.post("/community/candidates/{candidate_id}/decision")
def decide_candidate(candidate_id: int, body: Decision, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.get(ShortcutCandidate, candidate_id)
    if c is None:
        raise NotFound("Candidate not found")
    decide(db, c, body.decision, admin.id, body.note)
    db.commit()
    return candidate_dict(c)


@router.post("/community/mark-stale")
def run_mark_stale(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    changed = mark_stale(db)
    db.add(AuditLog(actor_user_id=admin.id, action="shortcut.mark_stale", details={"changed": changed}))
    db.commit()
    return {"marked_stale": changed}


@router.get("/community/submissions")
def submissions(status: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = select(RouteSubmission).order_by(RouteSubmission.id.desc())
    if status:
        stmt = stmt.where(RouteSubmission.status == status)
    return {"submissions": [submission_dict(s) for s in db.scalars(stmt.limit(500)).all()]}


@router.get("/incidents/pending")
def pending_incidents(db: Session = Depends(get_db)):
    rows = db.scalars(select(Incident).where(Incident.source == "community", Incident.status == "pending")).all()
    return {"incidents": [incident_dict(i) for i in rows]}


class IncidentDecision(BaseModel):
    decision: Literal["publish", "reject"]


@router.post("/incidents/{incident_id}/decision")
def moderate_incident(incident_id: int, body: IncidentDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    inc = db.get(Incident, incident_id)
    if inc is None or inc.source != "community":
        raise NotFound("Community incident not found")
    inc.status = "published" if body.decision == "publish" else "rejected"
    inc.active = body.decision == "publish"
    db.add(AuditLog(actor_user_id=admin.id, action=f"incident.{body.decision}", target=f"incident:{inc.id}"))
    db.commit()
    return incident_dict(inc)


@router.get("/data-freshness")
def data_freshness(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    return freshness_report(db, settings.observation_stale_minutes)


@router.get("/models")
def models(db: Session = Depends(get_db)):
    out = []
    for m in db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all():
        evals = db.scalars(select(EvaluationRecord).where(EvaluationRecord.model_version_id == m.id)).all()
        out.append({
            "id": m.id, "name": m.name, "version": m.version, "task": m.task, "algorithm": m.algorithm,
            "status": m.status, "dataset": m.dataset, "splits": m.splits, "params": m.params,
            "notes": m.notes, "created_at": m.created_at.isoformat() if m.created_at else None,
            "evaluations": [{"split": e.split, "horizon": e.horizon, "candidate": e.candidate, "metric": e.metric, "value": e.value, "n": e.n_samples} for e in evals],
        })
    return {"models": out}


@router.get("/system-health")
async def system_health(settings: Settings = Depends(settings_dep), db: Session = Depends(get_db)):
    checks = await dependency_report(settings)
    counts = {
        "users": db.scalar(select(func.count(User.id))),
        "trips": db.scalar(select(func.count(Trip.id))),
        "submissions": db.scalar(select(func.count(RouteSubmission.id))),
        "candidates": db.scalar(select(func.count(ShortcutCandidate.id))),
    }
    return {"checks": checks, "counts": counts, "environment": settings.environment, "version": settings.app_version}


@router.get("/audit-log")
def audit_log(limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return {"entries": [
        {"id": r.id, "actor_user_id": r.actor_user_id, "action": r.action, "target": r.target,
         "details": r.details, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]}
