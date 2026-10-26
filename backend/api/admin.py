"""Administrator endpoints. Every route depends on require_admin (role read from DB)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
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
    ProviderCall,
    TrafficObservation,
    TrafficSegment,
    WeatherObservation,
)
from db.session import get_db
from traffic.state_engine import freshness_report

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/intelligence/overview")
async def intelligence_overview(db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    """Read-only operational summary. Collector state is inferred from persisted observations."""
    from datetime import timedelta
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    freshness = freshness_report(db, settings.observation_stale_minutes)
    checks = await dependency_report(settings)
    traffic_last = db.scalar(select(func.max(TrafficObservation.ingested_at)))
    weather_last = db.scalar(select(func.max(WeatherObservation.ingested_at)))
    incident_last = db.scalar(select(func.max(Incident.last_seen_at)))
    recent_calls = db.scalars(select(ProviderCall).order_by(ProviderCall.called_at.desc()).limit(50)).all()
    count_since = now - timedelta(hours=24)
    traffic_24h = db.scalar(select(func.count(TrafficObservation.id)).where(TrafficObservation.ingested_at >= count_since)) or 0
    weather_24h = db.scalar(select(func.count(WeatherObservation.id)).where(WeatherObservation.ingested_at >= count_since)) or 0
    active_model = db.scalar(select(ModelVersion).where(ModelVersion.task == "segment_speed_ratio", ModelVersion.status == "active").order_by(ModelVersion.created_at.desc()).limit(1))

    def age(ts):
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0, int((now - ts).total_seconds()))

    def iso(ts):
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()

    # A successful SELECT 1 complements dependency_report's connection check.
    db.execute(text("SELECT 1"))
    return {
        "generated_at": now.isoformat(),
        "health_checks": checks,
        "database_query": "ok",
        "freshness": freshness,
        "collectors": {
            "enabled_setting": settings.collector_enabled,
            "worker_liveness": "not_instrumented",
            "enabled_setting_note": "COLLECTOR_ENABLED is not consulted by the separate collector process; service liveness is unknown.",
            "flow": {"status": "not_configured" if not settings.tomtom_key else ("unknown" if traffic_last is None else ("fresh" if (age(traffic_last) or 0) <= settings.observation_stale_minutes * 60 else "stale")), "interval_minutes": settings.collector_flow_interval_minutes, "last_ingested_at": iso(traffic_last), "age_seconds": age(traffic_last), "observations_last_24h": traffic_24h},
            "weather": {"status": "unknown" if weather_last is None else ("fresh" if (age(weather_last) or 0) <= settings.observation_stale_minutes * 60 else "stale"), "interval_minutes": settings.collector_weather_interval_minutes, "last_ingested_at": iso(weather_last), "age_seconds": age(weather_last), "observations_last_24h": weather_24h},
            "incidents": {"status": "not_configured" if not settings.tomtom_key else ("unknown" if incident_last is None else ("fresh" if (age(incident_last) or 0) <= settings.collector_incident_interval_minutes * 120 else "stale")), "interval_minutes": settings.collector_incident_interval_minutes, "last_seen_at": iso(incident_last), "age_seconds": age(incident_last)},
        },
        "production_forecast_model": ({"status": "active_registry_entry", "name": active_model.name, "version": active_model.version, "algorithm": active_model.algorithm, "task": active_model.task, "created_at": iso(active_model.created_at), "runtime_artifact_load_status": "not_checked"} if active_model else {"status": "none_active", "message": "No active segment forecasting model is registered; research artifacts are not production models."}),
        "request_metrics": {"status": "not_instrumented", "correlation_id": "X-Request-ID response header is available; request history and latency aggregates are not retained."},
        "latest_provider_calls": [{"provider": c.provider, "endpoint": c.endpoint, "purpose": c.purpose, "called_at": iso(c.called_at), "status_code": c.status_code, "ok": c.ok} for c in recent_calls],
        "telemetry_notes": ["Collector process liveness is not directly instrumented; freshness is derived from stored observations.", "Provider call records omit raw error text and credentials."],
    }


RESEARCH_DIR = Path(__file__).resolve().parents[1] / "evaluation" / "v2"


@router.get("/intelligence/research/{horizon}")
def intelligence_research(horizon: Literal["1d", "7d"], limit: int = Query(5000, ge=1, le=5000)):
    """Serve generated research summaries and bounded actual prediction rows."""
    data = {}
    for label, folder in (("statistical", "statistical"), ("transformer", "transformer"), ("ensemble", "ensemble")):
        summary = RESEARCH_DIR / folder / ("summary.json" if label != "ensemble" else f"{horizon}/summary.json")
        if summary.is_file():
            data[label] = json.loads(summary.read_text(encoding="utf-8"))
            # Persisted reports may contain a workstation-specific absolute path.
            if data[label].get("dataset"):
                data[label]["dataset"] = Path(str(data[label]["dataset"]).replace("\\", "/")).name
    prediction_path = RESEARCH_DIR / "ensemble" / horizon / "test_predictions.csv"
    predictions = []
    prediction_total = 0
    if prediction_path.is_file():
        with prediction_path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                prediction_total += 1
                if len(predictions) < limit:
                    predictions.append(row)
    def read_rows(path: Path):
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8") as stream:
            return list(csv.DictReader(stream))

    z_scores = [float(row["last_value_z_score"]) for row in read_rows(RESEARCH_DIR / "statistical" / horizon / "z_score_distribution.csv") if row.get("last_value_z_score")][:10000]
    error_by_series = read_rows(RESEARCH_DIR / "statistical" / horizon / "error_by_series.csv")[:5000]
    dataset_path = Path(data.get("ensemble", {}).get("dataset", ""))
    if not dataset_path.is_file():
        dataset_path = RESEARCH_DIR.parents[1] / "Banglore_traffic_Dataset.csv"
    try:
        with dataset_path.open(newline="", encoding="utf-8") as stream:
            dataset_columns = len(next(csv.reader(stream)))
    except (OSError, StopIteration):
        dataset_columns = None
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "horizon": horizon, "reports": data, "predictions": predictions, "prediction_count": len(predictions), "prediction_total": prediction_total, "predictions_truncated": prediction_total > len(predictions), "z_scores": z_scores, "error_by_series": error_by_series, "dataset_columns": dataset_columns}


@router.get("/intelligence/endpoints")
def intelligence_endpoints(request: Request):
    """Inventory the actual FastAPI route table without reading settings or secrets."""
    endpoints = []
    for path, operations in request.app.openapi().get("paths", {}).items():
        if not path.startswith("/v1/"):
            continue
        for method, operation in operations.items():
            if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            description = operation.get("summary") or operation.get("description") or ""
            endpoints.append({"path": path, "method": method.upper(), "description": description.splitlines()[0][:180]})
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "endpoints": sorted(endpoints, key=lambda x: (x["path"], x["method"]))}


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


@router.get("/forecast/online")
def forecast_online(db: Session = Depends(get_db)):
    """Prospective prediction-versus-actual error of the logged baselines."""

    from forecasting.online import report

    return report(db)


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
