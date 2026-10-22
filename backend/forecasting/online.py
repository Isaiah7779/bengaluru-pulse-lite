"""Prospective (online) forecast logging and prediction-versus-actual evaluation.

Every flow sweep the collector:

1. **logs** forecasts made *now* for each monitored segment and horizon
   (30/60/120 min) by each baseline, using only observations already stored;
2. **resolves** earlier forecasts whose target time has passed, by attaching
   the observed value for that target bucket;
3. the **report** compares predictions with what actually happened.

Definitions (see docs/RESEARCH_MILESTONE_FORECASTING.md):

* Time grid: 30-minute UTC buckets. An observation's time is when the collector
  fetched it (TomTom flow responses carry no measurement timestamp).
* Target: mean speed ratio (current / free-flow) of a segment's observations in
  the target bucket. No interpolation: a bucket without observations has no
  actual value and is counted as missing, never filled in.
* Origin: the bucket containing ``now``; a segment is forecast only if it was
  observed in that bucket (a fresh last value exists).
* Baselines: persistence (origin value), seasonal naive (same bucket one week
  before the target), historical average (mean of all earlier same weekday and
  time-of-day buckets before the origin). Baselines lacking history are skipped,
  not substituted, and the report counts each candidate's own sample size.

This makes no TomTom requests; it reads the database only.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from db.models import ModelVersion, PredictionRecord, TrafficObservation, TrafficSegment, as_utc
from forecasting.predictor import SEGMENT_TASK

logger = logging.getLogger("pulse.forecast.online")

STEP = timedelta(minutes=30)
HORIZONS_MIN = (30, 60, 120)
WEEK = timedelta(days=7)
HISTORY = timedelta(days=29)  # enough for four weekly samples per slot
BASELINES = ("persistence", "seasonal_naive", "historical_average")
VERSION = "online-v1"
# A target bucket still without observations this long after it ended is "missing".
MISSING_AFTER = timedelta(hours=2)


def bucket(ts: datetime) -> datetime:
    ts = as_utc(ts)
    return ts.replace(minute=(ts.minute // 30) * 30, second=0, microsecond=0)


def baseline_versions(session: Session) -> Dict[str, int]:
    """Registry rows identifying each baseline's logged predictions (status 'baseline')."""

    ids: Dict[str, int] = {}
    for name in BASELINES:
        mv = session.scalar(
            select(ModelVersion).where(ModelVersion.name == f"baseline-{name}", ModelVersion.version == VERSION)
        )
        if mv is None:
            mv = ModelVersion(
                name=f"baseline-{name}", version=VERSION, task=SEGMENT_TASK, algorithm=f"baseline:{name}",
                dataset="collected TomTom flow observations (prospective)", status="baseline",
                notes="Prospective prediction-vs-actual logging; see forecasting/online.py",
            )
            session.add(mv)
            session.flush()
        ids[name] = mv.id
    return ids


def segment_series(session: Session, segment_id: int, start: datetime, end: datetime) -> Dict[datetime, float]:
    """Mean speed ratio per 30-min bucket for observations with start <= time < end."""

    rows = session.execute(
        select(TrafficObservation.observed_at, TrafficObservation.speed_ratio).where(
            TrafficObservation.segment_id == segment_id,
            TrafficObservation.observed_at >= start,
            TrafficObservation.observed_at < end,
        )
    ).all()
    acc: Dict[datetime, List[float]] = defaultdict(list)
    for ts, value in rows:
        acc[bucket(ts)].append(float(value))
    return {b: sum(v) / len(v) for b, v in acc.items()}


def baseline_predictions(history: Dict[datetime, float], origin: datetime, target: datetime) -> Dict[str, Optional[float]]:
    """Predictions for ``target`` from buckets at or before ``origin`` only."""

    usable = {b: v for b, v in history.items() if b <= origin}
    same_slot = [v for b, v in usable.items() if (target - b) >= WEEK and (target - b) % WEEK == timedelta(0)]
    return {
        "persistence": usable.get(origin),
        "seasonal_naive": usable.get(target - WEEK),
        "historical_average": sum(same_slot) / len(same_slot) if same_slot else None,
    }


def log_forecasts(session: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    now = as_utc(now or datetime.now(timezone.utc))
    origin = bucket(now)
    versions = baseline_versions(session)
    stats = {"segments_forecast": 0, "segments_without_fresh_obs": 0, "logged": 0, "already_logged": 0, "skipped_no_history": 0}
    segments = session.scalars(select(TrafficSegment.id).where(TrafficSegment.active.is_(True))).all()
    for seg_id in segments:
        # Only observations that exist at forecast time: strictly before `now`.
        history = segment_series(session, seg_id, origin - HISTORY, now + timedelta(microseconds=1))
        if origin not in history:
            stats["segments_without_fresh_obs"] += 1
            continue
        stats["segments_forecast"] += 1
        for minutes in HORIZONS_MIN:
            target = origin + timedelta(minutes=minutes)
            for name, value in baseline_predictions(history, origin, target).items():
                if value is None:
                    stats["skipped_no_history"] += 1
                    continue
                exists = session.scalar(
                    select(PredictionRecord.id).where(
                        PredictionRecord.model_version_id == versions[name], PredictionRecord.segment_id == seg_id,
                        PredictionRecord.target_time == target, PredictionRecord.horizon_minutes == minutes,
                    )
                )
                if exists:
                    stats["already_logged"] += 1
                    continue
                session.add(PredictionRecord(
                    model_version_id=versions[name], segment_id=seg_id, made_at=now, target_time=target,
                    horizon_minutes=minutes, predicted_value=round(value, 5),
                ))
                stats["logged"] += 1
    session.flush()
    return stats


def resolve_actuals(session: Session, now: Optional[datetime] = None) -> Dict[str, int]:
    """Attach observed values to forecasts whose target bucket has ended."""

    now = as_utc(now or datetime.now(timezone.utc))
    pending = session.scalars(
        select(PredictionRecord).where(PredictionRecord.actual_value.is_(None), PredictionRecord.target_time <= now - STEP)
    ).all()
    cache: Dict[Tuple[int, datetime], Optional[float]] = {}
    resolved = 0
    for rec in pending:
        target = as_utc(rec.target_time)
        key = (rec.segment_id, target)
        if key not in cache:
            cache[key] = segment_series(session, rec.segment_id, target, target + STEP).get(target)
        if cache[key] is not None:
            rec.actual_value = round(cache[key], 5)
            resolved += 1
    session.flush()
    return {"pending_checked": len(pending), "resolved": resolved}


def _metrics(pairs: Iterable[Tuple[float, float]]) -> Dict[str, Optional[float]]:
    pairs = list(pairs)
    if not pairs:
        return {"n": 0, "mae": None, "rmse": None, "bias": None}
    errors = [p - a for p, a in pairs]
    return {
        "n": len(pairs),
        "mae": round(sum(abs(e) for e in errors) / len(errors), 5),
        "rmse": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 5),
        "bias": round(sum(errors) / len(errors), 5),
    }


def report(session: Session, now: Optional[datetime] = None) -> Dict:
    """Prediction-versus-actual error per baseline and horizon.

    ``paired`` restricts every candidate to the (segment, target, horizon)
    triples for which *all* candidates have a resolved forecast, so their errors
    are directly comparable.
    """

    now = as_utc(now or datetime.now(timezone.utc))
    existing = session.execute(
        select(ModelVersion.id, ModelVersion.name).where(
            ModelVersion.version == VERSION, ModelVersion.name.in_([f"baseline-{b}" for b in BASELINES])
        )
    ).all()
    versions = {mv_id: name.removeprefix("baseline-") for mv_id, name in existing}
    rows = [] if not versions else session.execute(
        select(PredictionRecord).where(PredictionRecord.model_version_id.in_(list(versions)))
    ).scalars().all()
    by = defaultdict(lambda: {"resolved": [], "pending": 0, "missing": 0})
    triples: Dict[Tuple[int, datetime, int], Dict[str, Tuple[float, float]]] = defaultdict(dict)
    first = last = None
    for r in rows:
        name = versions[r.model_version_id]
        target = as_utc(r.target_time)
        slot = by[(name, r.horizon_minutes)]
        if r.actual_value is not None:
            slot["resolved"].append((r.predicted_value, r.actual_value))
            triples[(r.segment_id, target, r.horizon_minutes)][name] = (r.predicted_value, r.actual_value)
        elif target + STEP + MISSING_AFTER <= now:
            slot["missing"] += 1
        else:
            slot["pending"] += 1
        made = as_utc(r.made_at)
        first = made if first is None or made < first else first
        last = made if last is None or made > last else last
    out: Dict = {
        "generated_at": now.isoformat(),
        "kind": "prospective prediction-vs-actual (baselines only)",
        "forecasts_logged": len(rows),
        "logging_period": [first.isoformat() if first else None, last.isoformat() if last else None],
        "candidates": {},
        "paired": {},
    }
    for (name, minutes), slot in sorted(by.items()):
        out["candidates"].setdefault(name, {})[f"{minutes}m"] = {
            **_metrics(slot["resolved"]), "pending": slot["pending"], "missing_actual": slot["missing"],
        }
    for minutes in HORIZONS_MIN:
        complete = [t for k, t in triples.items() if k[2] == minutes and len(t) == len(BASELINES)]
        if complete:
            out["paired"][f"{minutes}m"] = {name: _metrics(t[name] for t in complete) for name in BASELINES}
    return out


def run_cycle(now: Optional[datetime] = None) -> Dict:
    """Resolve due forecasts, then log new ones (called after each flow sweep)."""

    from db.session import session_scope

    with session_scope() as session:
        resolved = resolve_actuals(session, now)
        logged = log_forecasts(session, now)
    return {"resolved": resolved, "logged": logged}


def main() -> None:
    from core.log_config import configure_logging
    from db.session import session_scope

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["report", "cycle"])
    args = parser.parse_args()
    configure_logging("WARNING")
    if args.command == "cycle":
        print(json.dumps(run_cycle(), indent=2, default=str))
    else:
        with session_scope() as session:
            print(json.dumps(report(session), indent=2, default=str))


if __name__ == "__main__":
    main()
