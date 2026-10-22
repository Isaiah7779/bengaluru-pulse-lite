"""Reproducible forecasting pipeline: validate â†’ features â†’ baselines â†’ models â†’
chronological evaluation â†’ registry.

    python -m forecasting.pipeline research   # public daily dataset (day-ahead)
    python -m forecasting.pipeline segments   # collected TomTom observations (30/60/120 min)

Principles
* Splits are chronological by *target time* (train < validation < test); the
  test period is evaluated once, after model selection on validation.
* Baselines first: persistence, seasonal naive, historical average.
* Every number written to the registry/report is measured by this code.
* A model is marked `active` (used by routing) only if it beats the best
  baseline on the test period by ACTIVATION_MIN_IMPROVEMENT with enough samples.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("pulse.forecasting")

ACTIVATION_MIN_IMPROVEMENT = 0.05  # 5% lower test MAE than the best baseline
SEED = 42


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    err = y_pred - y_true
    nonzero = np.abs(y_true) > 1e-9
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2)) or float("nan")
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(math.sqrt(np.mean(err**2))),
        "mape": float(np.mean(np.abs(err[nonzero] / y_true[nonzero])) * 100) if nonzero.any() else float("nan"),
        "smape": float(np.mean(2 * np.abs(err) / (np.abs(y_true) + np.abs(y_pred) + 1e-9)) * 100),
        "r2": 1 - ss_res / ss_tot,
        "bias": float(np.mean(err)),
        "n": int(len(y_true)),
    }


# ---------------------------------------------------------------------------
# task configuration
# ---------------------------------------------------------------------------


@dataclass
class TaskConfig:
    name: str
    task: str
    dataset: str
    target: str
    freq: str  # pandas offset alias of the regular grid
    horizons: Dict[str, int]  # label -> steps ahead
    lags: Sequence[int]
    rolls: Sequence[int]
    season: int  # steps in one seasonal period (for seasonal naive)
    slot_fn: Callable[[pd.Series], pd.Series]  # time -> seasonal slot key for historical average
    calendar: Callable[[pd.Series], pd.DataFrame]
    val_fraction: float = 0.15
    test_fraction: float = 0.2
    min_series_points: int = 30
    min_test_samples: int = 200
    min_span_days: float = 14.0
    clip: Tuple[float, float] = (0.0, float("inf"))
    notes: str = ""


def daily_calendar(ts: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"dow": ts.dt.dayofweek, "month": ts.dt.month, "doy_sin": np.sin(2 * np.pi * ts.dt.dayofyear / 365.25),
                         "doy_cos": np.cos(2 * np.pi * ts.dt.dayofyear / 365.25)}, index=ts.index)


def intraday_calendar(ts: pd.Series) -> pd.DataFrame:
    local = ts.dt.tz_convert("Asia/Kolkata") if ts.dt.tz is not None else ts
    minutes = local.dt.hour * 60 + local.dt.minute
    return pd.DataFrame({"hod_sin": np.sin(2 * np.pi * minutes / 1440), "hod_cos": np.cos(2 * np.pi * minutes / 1440),
                         "dow": local.dt.dayofweek, "weekend": (local.dt.dayofweek >= 5).astype(int)}, index=ts.index)


def _intraday_slot(ts: pd.Series) -> pd.Series:
    local = ts.dt.tz_convert("Asia/Kolkata") if ts.dt.tz is not None else ts
    return local.dt.dayofweek.astype(str) + "-" + (local.dt.hour * 2 + local.dt.minute // 30).astype(str)


RESEARCH = TaskConfig(
    name="research-daily-congestion",
    task="road_congestion_day_ahead",
    dataset="Banglore_traffic_Dataset.csv (public, daily, 16 roads)",
    target="congestion",
    freq="D",
    horizons={"1d": 1, "7d": 7},
    lags=(0, 1, 2, 6),
    rolls=(7, 28),
    season=7,
    slot_fn=lambda ts: ts.dt.dayofweek.astype(str),
    calendar=daily_calendar,
    clip=(0.0, 100.0),
    min_test_samples=200,
    min_span_days=365,
    notes="Day-ahead congestion level per road. Same-day volume/speed are NOT used (unknown at forecast time).",
)

SEGMENTS = TaskConfig(
    name="segment-speed-ratio",
    task="segment_speed_ratio",
    dataset="Bengaluru Pulse collected TomTom flow observations (26 monitored points)",
    target="speed_ratio",
    freq="30min",
    horizons={"30m": 1, "60m": 2, "120m": 4},
    lags=(0, 1, 2, 47, 335),
    rolls=(4, 48),
    season=336,  # one week of 30-minute slots
    slot_fn=_intraday_slot,
    calendar=intraday_calendar,
    clip=(0.0, 1.5),
    min_test_samples=500,
    min_span_days=14,
    notes="Current/free-flow speed ratio at monitored points, 30-120 minutes ahead.",
)


# ---------------------------------------------------------------------------
# data loading + validation
# ---------------------------------------------------------------------------


def load_research(path: Path) -> Tuple[pd.DataFrame, Dict]:
    raw = pd.read_csv(path, parse_dates=["Date"])
    report: Dict = {"rows_raw": int(len(raw))}
    raw["series"] = raw["Area Name"].str.strip() + " | " + raw["Road/Intersection Name"].str.strip()
    df = raw.rename(columns={"Date": "time", "Congestion Level": "congestion"})[["series", "time", "congestion"]]
    report["duplicates_dropped"] = int(df.duplicated(["series", "time"]).sum())
    df = df.drop_duplicates(["series", "time"])
    report["nulls_dropped"] = int(df["congestion"].isna().sum())
    df = df.dropna(subset=["congestion"])
    out_of_range = ~df["congestion"].between(0, 100)
    report["out_of_range_dropped"] = int(out_of_range.sum())
    df = df[~out_of_range]
    report["share_at_cap_100"] = round(float((df["congestion"] >= 100).mean()), 4)
    lag1 = []
    for _, g in df.sort_values("time").groupby("series"):
        s = g["congestion"].to_numpy()
        if len(s) > 30:
            lag1.append(float(np.corrcoef(s[:-1], s[1:])[0, 1]))
    report["lag1_autocorrelation_mean"] = round(float(np.mean(lag1)), 4)
    report["lag1_autocorrelation_range"] = [round(min(lag1), 4), round(max(lag1), 4)]
    report["dow_mean_spread"] = round(float(df.groupby(df.time.dt.dayofweek)["congestion"].mean().agg(np.ptp)), 3)
    return df, report


def load_segments() -> Tuple[pd.DataFrame, Dict]:
    from sqlalchemy import select

    from db.models import TrafficObservation
    from db.session import session_scope

    with session_scope() as s:
        rows = s.execute(
            select(TrafficObservation.segment_id, TrafficObservation.observed_at, TrafficObservation.speed_ratio,
                   TrafficObservation.confidence)
        ).all()
    df = pd.DataFrame(rows, columns=["series", "time", "speed_ratio", "confidence"])
    report: Dict = {"rows_raw": int(len(df))}
    if df.empty:
        return df, report
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.floor("30min")
    low_conf = df["confidence"].notna() & (df["confidence"] < 0.5)
    report["low_confidence_dropped"] = int(low_conf.sum())
    df = df[~low_conf]
    report["duplicates_merged"] = int(df.duplicated(["series", "time"]).sum())
    df = df.groupby(["series", "time"], as_index=False)["speed_ratio"].mean()
    return df, report


# ---------------------------------------------------------------------------
# feature construction
# ---------------------------------------------------------------------------


def to_grid(df: pd.DataFrame, cfg: TaskConfig) -> pd.DataFrame:
    """Regular per-series grid with NaN where nothing was observed."""

    frames = []
    for sid, g in df.groupby("series"):
        g = g.set_index("time").sort_index()
        full = g[[cfg.target]].asfreq(cfg.freq)
        full["series"] = sid
        frames.append(full.reset_index())
    return pd.concat(frames, ignore_index=True)


def supervised(grid: pd.DataFrame, cfg: TaskConfig, horizon: int) -> pd.DataFrame:
    """One row per (series, origin time) with a known target `horizon` steps ahead."""

    out = []
    for sid, g in grid.groupby("series"):
        g = g.sort_values("time").reset_index(drop=True)
        y = g[cfg.target]
        feat = pd.DataFrame({"series": sid, "origin": g["time"]})
        last = y.ffill()
        feat["last_value"] = last
        observed_idx = pd.Series(np.where(y.notna(), np.arange(len(y)), np.nan)).ffill()
        feat["last_age_steps"] = np.arange(len(y)) - observed_idx
        for lag in cfg.lags:
            feat[f"lag_{lag}"] = y.shift(lag)
        for w in cfg.rolls:
            feat[f"roll_mean_{w}"] = y.rolling(w, min_periods=max(1, w // 4)).mean()
            feat[f"roll_std_{w}"] = y.rolling(w, min_periods=max(2, w // 4)).std()
        seasonal_idx = horizon - cfg.season
        feat["seasonal_value"] = y.shift(-seasonal_idx) if seasonal_idx < 0 else y.shift(seasonal_idx)
        feat["target_time"] = g["time"].shift(-horizon)
        feat["target"] = y.shift(-horizon)
        out.append(feat)
    data = pd.concat(out, ignore_index=True)
    data = data[data["target"].notna() & data["last_value"].notna()].reset_index(drop=True)
    cal = cfg.calendar(data["target_time"])
    return pd.concat([data, cal.add_prefix("t_")], axis=1)


def chronological_split(data: pd.DataFrame, cfg: TaskConfig) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    times = np.sort(data["target_time"].unique())
    n = len(times)
    val_start = times[int(n * (1 - cfg.test_fraction - cfg.val_fraction))]
    test_start = times[int(n * (1 - cfg.test_fraction))]
    train = data[data["target_time"] < val_start]
    val = data[(data["target_time"] >= val_start) & (data["target_time"] < test_start)]
    test = data[data["target_time"] >= test_start]
    # Features must not peek past the split boundary: drop origins whose target lies across it.
    splits = {
        "train": [str(pd.Timestamp(train["target_time"].min())), str(pd.Timestamp(train["target_time"].max()))],
        "validation": [str(pd.Timestamp(val["target_time"].min())), str(pd.Timestamp(val["target_time"].max()))],
        "test": [str(pd.Timestamp(test["target_time"].min())), str(pd.Timestamp(test["target_time"].max()))],
        "sizes": {"train": len(train), "validation": len(val), "test": len(test)},
    }
    return train, val, test, splits


# ---------------------------------------------------------------------------
# baselines + models
# ---------------------------------------------------------------------------


def historical_average_table(train: pd.DataFrame, cfg: TaskConfig) -> Tuple[pd.Series, pd.Series, float]:
    slots = cfg.slot_fn(train["target_time"])
    by_slot = train.groupby([train["series"], slots])["target"].mean()
    by_series = train.groupby("series")["target"].mean()
    return by_slot, by_series, float(train["target"].mean())


def predict_historical(df: pd.DataFrame, cfg: TaskConfig, table) -> np.ndarray:
    by_slot, by_series, overall = table
    slots = cfg.slot_fn(df["target_time"])
    keys = list(zip(df["series"], slots))
    out = []
    for (sid, slot) in keys:
        if (sid, slot) in by_slot.index:
            out.append(by_slot[(sid, slot)])
        elif sid in by_series.index:
            out.append(by_series[sid])
        else:
            out.append(overall)
    return np.asarray(out, float)


def feature_columns(data: pd.DataFrame) -> List[str]:
    return [c for c in data.columns if c not in {"series", "origin", "target_time", "target"}]


def model_matrix(df: pd.DataFrame, cols: List[str], table, cfg: TaskConfig) -> np.ndarray:
    X = df[cols].copy()
    X["hist_avg"] = predict_historical(df, cfg, table)  # computed from training data only
    return X


@dataclass
class Candidate:
    name: str
    factory: Callable[[], object]
    params: Dict = field(default_factory=dict)


def candidates() -> List[Candidate]:
    out = [Candidate("ridge", lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)), {"alpha": 1.0})]
    for lr in (0.05, 0.1):
        for leaves in (15, 31):
            params = {"learning_rate": lr, "max_leaf_nodes": leaves, "max_iter": 300, "l2_regularization": 1.0}
            out.append(Candidate(
                f"hgb_lr{lr}_l{leaves}",
                lambda p=params: HistGradientBoostingRegressor(random_state=SEED, early_stopping=False, **p),
                params,
            ))
    return out


def _fit_predict(model, X_train, y_train, X_eval):
    X_train = X_train.fillna(X_train.median(numeric_only=True))
    model.fit(X_train, y_train)
    return model.predict(X_eval.fillna(X_train.median(numeric_only=True)))


# ---------------------------------------------------------------------------
# experiment
# ---------------------------------------------------------------------------


def run_horizon(grid: pd.DataFrame, cfg: TaskConfig, label: str, steps: int) -> Dict:
    data = supervised(grid, cfg, steps)
    train, val, test, splits = chronological_split(data, cfg)
    lo, hi = cfg.clip
    table = historical_average_table(train, cfg)
    result: Dict = {"horizon": label, "steps": steps, "splits": splits, "validation": {}, "test": {}}

    def baseline_preds(df):
        seasonal = df["seasonal_value"].fillna(df["last_value"]).to_numpy()
        return {
            "persistence": df["last_value"].to_numpy(),
            "seasonal_naive": seasonal,
            "historical_average": predict_historical(df, cfg, table),
        }

    for split_name, df in (("validation", val), ("test", test)):
        for name, pred in baseline_preds(df).items():
            result[split_name][f"baseline:{name}"] = metrics(df["target"], np.clip(pred, lo, hi))

    cols = feature_columns(data)
    X_train, X_val = model_matrix(train, cols, table, cfg), model_matrix(val, cols, table, cfg)
    best_name, best_mae, best_cand = None, float("inf"), None
    for cand in candidates():
        pred = np.clip(_fit_predict(cand.factory(), X_train, train["target"], X_val), lo, hi)
        m = metrics(val["target"], pred)
        result["validation"][f"model:{cand.name}"] = m
        if m["mae"] < best_mae:
            best_name, best_mae, best_cand = cand.name, m["mae"], cand

    # Refit the selected model on train+validation, evaluate on test once.
    trainval = pd.concat([train, val])
    table_tv = historical_average_table(trainval, cfg)
    X_tv = model_matrix(trainval, cols, table_tv, cfg)
    X_test = model_matrix(test, cols, table_tv, cfg)
    final = best_cand.factory()
    pred_test = np.clip(_fit_predict(final, X_tv, trainval["target"], X_test), lo, hi)
    result["test"][f"model:{best_name}"] = metrics(test["target"], pred_test)
    # Historical average refit on train+val too, for a fair test comparison.
    result["test"]["baseline:historical_average"] = metrics(
        test["target"], np.clip(predict_historical(test, cfg, table_tv), lo, hi)
    )
    best_baseline = min(
        ((k, v["mae"]) for k, v in result["test"].items() if k.startswith("baseline:")), key=lambda kv: kv[1]
    )
    model_mae = result["test"][f"model:{best_name}"]["mae"]
    improvement = 1 - model_mae / best_baseline[1] if best_baseline[1] > 0 else 0.0
    result["selected_model"] = best_name
    result["selected_params"] = best_cand.params
    result["best_baseline"] = best_baseline[0]
    result["test_improvement_vs_best_baseline"] = round(improvement, 4)
    result["_artifact"] = {"model": final, "columns": cols, "hist_table": table_tv, "fill": X_tv.median(numeric_only=True)}
    return result


def run(cfg: TaskConfig, df: pd.DataFrame, data_report: Dict, out_dir: Path, register: bool = True) -> Dict:
    span_days = (df["time"].max() - df["time"].min()).total_seconds() / 86400 if len(df) else 0.0
    report: Dict = {
        "task": cfg.task, "name": cfg.name, "dataset": cfg.dataset, "notes": cfg.notes,
        "generated_at": datetime.now(timezone.utc).isoformat(), "data_validation": data_report,
        "series": int(df["series"].nunique()) if len(df) else 0, "observations": int(len(df)),
        "span_days": round(span_days, 2),
        "period": [str(df["time"].min()), str(df["time"].max())] if len(df) else None,
    }
    if span_days < cfg.min_span_days or report["series"] == 0:
        report["status"] = "insufficient_data"
        report["reason"] = f"{span_days:.1f} days collected; at least {cfg.min_span_days} days required for a chronological train/validation/test evaluation"
        _write(report, out_dir)
        return report

    grid = to_grid(df, cfg)
    horizons = {}
    for label, steps in cfg.horizons.items():
        try:
            horizons[label] = run_horizon(grid, cfg, label, steps)
        except Exception as exc:  # report, don't hide
            logger.exception("Horizon %s failed", label)
            horizons[label] = {"error": f"{type(exc).__name__}: {exc}"}
    report["horizons"] = {k: {kk: vv for kk, vv in v.items() if kk != "_artifact"} for k, v in horizons.items()}

    ok = [h for h in horizons.values() if "error" not in h]
    passes = [
        h for h in ok
        if h["test_improvement_vs_best_baseline"] >= ACTIVATION_MIN_IMPROVEMENT
        and h["splits"]["sizes"]["test"] >= cfg.min_test_samples
    ]
    report["activation"] = {
        "rule": f"test MAE >= {ACTIVATION_MIN_IMPROVEMENT:.0%} below the best baseline, >= {cfg.min_test_samples} test samples, every horizon",
        "horizons_passing": [h["horizon"] for h in passes],
        "activated": bool(ok) and len(passes) == len(cfg.horizons),
    }
    report["status"] = "evaluated"
    version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    artifact_path = out_dir.parent.parent / "models" / f"{cfg.name}-{version}.joblib"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"config": cfg.name, "task": cfg.task, "freq": cfg.freq, "horizons": cfg.horizons,
                 "models": {k: v["_artifact"] for k, v in horizons.items() if "_artifact" in v},
                 "selected": {k: v.get("selected_model") for k, v in horizons.items()}}, artifact_path)
    report["artifact"] = artifact_path.name
    if register:
        report["model_version_id"] = _register(cfg, report, version, artifact_path, df)
    _write(report, out_dir)
    return report


def _register(cfg: TaskConfig, report: Dict, version: str, artifact: Path, df: pd.DataFrame) -> int:
    from sqlalchemy import update

    from db.models import EvaluationRecord, ModelVersion
    from db.session import session_scope

    status = "active" if report["activation"]["activated"] else "candidate"
    with session_scope() as s:
        if status == "active":
            s.execute(update(ModelVersion).where(ModelVersion.task == cfg.task, ModelVersion.status == "active").values(status="retired"))
        first = next(iter(report["horizons"].values()))
        mv = ModelVersion(
            name=cfg.name, version=version, task=cfg.task,
            algorithm=", ".join(f"{h}:{r.get('selected_model')}" for h, r in report["horizons"].items()),
            dataset=cfg.dataset,
            dataset_start=pd.Timestamp(df["time"].min()).to_pydatetime(),
            dataset_end=pd.Timestamp(df["time"].max()).to_pydatetime(),
            splits={h: r.get("splits") for h, r in report["horizons"].items()},
            params={h: r.get("selected_params") for h, r in report["horizons"].items()},
            features=None, artifact_path=artifact.name, status=status,
            notes=f"{cfg.notes} Activation: {report['activation']}",
        )
        s.add(mv)
        s.flush()
        for horizon, r in report["horizons"].items():
            for split in ("validation", "test"):
                for name, m in (r.get(split) or {}).items():
                    for metric in ("mae", "rmse", "smape", "r2"):
                        value = m.get(metric)
                        if value is None or (isinstance(value, float) and math.isnan(value)):
                            continue
                        s.add(EvaluationRecord(model_version_id=mv.id, split=split, horizon=horizon, candidate=name,
                                               metric=metric, value=float(value), n_samples=int(m["n"])))
        return mv.id


def _write(report: Dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report['name']}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    logger.info("Report written: %s", path)


def legacy_nowcast_check(path: Path) -> Dict:
    """Re-evaluate the V1 approach (same-day volume & speed as inputs) chronologically.

    This is *estimation* of a same-day value from other same-day measurements,
    not forecasting; it explains where the V1 R² came from.
    """

    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import train_test_split

    raw = pd.read_csv(path, parse_dates=["Date"]).sort_values("Date")
    X = pd.DataFrame({
        "volume": raw["Traffic Volume"], "speed": raw["Average Speed"],
        "road": raw["Road/Intersection Name"].astype("category").cat.codes,
        "area": raw["Area Name"].astype("category").cat.codes,
        "weather": raw["Weather Conditions"].astype("category").cat.codes,
    })
    y = raw["Congestion Level"].to_numpy()
    cut = raw["Date"].quantile(0.8)
    tr, te = (raw["Date"] < cut).to_numpy(), (raw["Date"] >= cut).to_numpy()
    rf = RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1)
    chrono = metrics(y[te], rf.fit(X[tr], y[tr]).predict(X[te]))
    Xa, Xb, ya, yb = train_test_split(X, y, test_size=0.2, random_state=SEED)
    rand = metrics(yb, RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1).fit(Xa, ya).predict(Xb))
    without = metrics(y[te], RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1)
                      .fit(X[tr][["road", "area", "weather"]], y[tr]).predict(X[te][["road", "area", "weather"]]))
    return {
        "description": "V1-style same-day estimation (inputs include same-day volume and speed) — not a forecast",
        "chronological_split_test": chrono,
        "random_split_test": rand,
        "chronological_without_same_day_measurements": without,
        "test_period_start": str(cut.date()),
    }


def main() -> None:
    from core.log_config import configure_logging
    from core.settings import BASE_DIR, get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=["research", "segments"])
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    configure_logging("INFO")
    np.random.seed(SEED)
    out_dir = BASE_DIR / "evaluation" / "v2"
    if args.task == "research":
        df, rep = load_research(get_settings().dataset_path)
        rep["legacy_nowcast_check"] = legacy_nowcast_check(get_settings().dataset_path)
        result = run(RESEARCH, df, rep, out_dir, register=not args.no_register)
        print(json.dumps({k: {m: round(v[m], 4) for m in ("mae", "rmse", "r2")} for k, v in rep["legacy_nowcast_check"].items() if isinstance(v, dict)}, indent=2))
    else:
        df, rep = load_segments()
        result = run(SEGMENTS, df, rep, out_dir, register=not args.no_register)
    summary = {k: result.get(k) for k in ("status", "reason", "observations", "span_days", "activation")}
    for h, r in (result.get("horizons") or {}).items():
        if "test" in r:
            summary[h] = {k: round(v["mae"], 4) for k, v in r["test"].items()} | {"improvement": r["test_improvement_vs_best_baseline"]}
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
