"""Validation-weighted, research-only ensemble evaluation.

Run from ``backend`` with ``python -m evaluation.v2.ensemble_evaluation``.
Weights are fitted on validation predictions only. Test outputs are loaded from the
Stage 3 Transformer evaluation and scored once after weights have been fixed.
Nothing is registered or connected to routing/model activation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from core.settings import get_settings
from evaluation.v2.statistical_evaluation import calculate_metrics, run_research_evaluation
from forecasting.pipeline import (
    RESEARCH,
    candidates,
    chronological_split,
    feature_columns,
    historical_average_table,
    load_research,
    model_matrix,
    supervised,
    to_grid,
)
from forecasting.transformer_experiment import (
    TransformerConfig,
    build_sequences,
    fit_transformer,
)

COMPONENTS = ("ridge", "histogram_gradient_boosting", "transformer")
BASELINES = ("persistence", "seasonal_naive", "historical_average")
ALL_MODELS = BASELINES + COMPONENTS
WEIGHT_GRID_STEP = 0.01


def _keys(frame: pd.DataFrame) -> set:
    return set(zip(frame.series.astype(str), pd.to_datetime(frame.target_time, utc=True)))


def _valid_rows(frame: pd.DataFrame, model_names: Iterable[str]) -> Tuple[pd.DataFrame, int]:
    """Keep rows with a finite actual and every required prediction; never impute forecasts."""
    pred_cols = [f"{name}_prediction" for name in model_names]
    absent = [col for col in ["series", "target_time", "actual", *pred_cols] if col not in frame]
    if absent:
        raise ValueError(f"Prediction frame is missing columns: {absent}")
    if frame.duplicated(["series", "target_time"]).any():
        raise ValueError("Prediction frame contains duplicate (series, target_time) keys")
    values = frame[["actual", *pred_cols]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(values).all(axis=1)
    return frame.loc[valid].copy().reset_index(drop=True), int((~valid).sum())


def align_prediction_frames(actual_rows: pd.DataFrame, prediction_frames: Dict[str, pd.DataFrame],
                            model_names: Iterable[str]) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Align on the shared key intersection and return complete, finite rows."""
    joined = actual_rows[["series", "target_time", "actual"]].copy()
    joined["series"] = joined.series.astype(str)
    joined["target_time"] = pd.to_datetime(joined.target_time, utc=True)
    if joined.duplicated(["series", "target_time"]).any():
        raise ValueError("Actual rows contain duplicate (series, target_time) keys")
    common_keys = _keys(joined)
    for name in model_names:
        frame = prediction_frames[name].copy()
        frame["series"] = frame.series.astype(str)
        frame["target_time"] = pd.to_datetime(frame.target_time, utc=True)
        if frame.duplicated(["series", "target_time"]).any():
            raise ValueError(f"{name} predictions contain duplicate (series, target_time) keys")
        prediction_keys = _keys(frame)
        if prediction_keys - _keys(joined):
            raise ValueError(f"{name} predictions include target rows absent from the actual evaluation")
        pred_col = f"{name}_prediction"
        if pred_col not in frame:
            raise ValueError(f"{name} predictions are missing {pred_col}")
        common_keys &= prediction_keys
    if not common_keys:
        raise ValueError("No common chronological rows are available across model predictions")
    joined = joined.loc[[key in common_keys for key in zip(joined.series.astype(str), joined.target_time)]].copy()
    for name in model_names:
        frame = prediction_frames[name].copy()
        frame["series"] = frame.series.astype(str)
        frame["target_time"] = pd.to_datetime(frame.target_time, utc=True)
        pred_col = f"{name}_prediction"
        joined = joined.merge(frame[["series", "target_time", pred_col]], on=["series", "target_time"],
                              how="inner", validate="one_to_one")
    complete, dropped = _valid_rows(joined, model_names)
    drop_counts = {"missing_prediction_key_rows": len(actual_rows) - len(common_keys),
                   "incomplete_or_nonfinite_rows": dropped}
    return complete, drop_counts


def enumerate_weight_grid(model_count: int, step: float = WEIGHT_GRID_STEP) -> np.ndarray:
    """Deterministic simplex grid with nonnegative weights summing to one."""
    if model_count < 2 or step <= 0 or step > 1:
        raise ValueError("At least two models and a weight step in (0, 1] are required")
    units = round(1 / step)
    if not np.isclose(units * step, 1.0):
        raise ValueError("Weight grid step must divide 1 exactly")
    weights = []

    def recurse(prefix: List[int], remaining: int, slots: int) -> None:
        if slots == 1:
            weights.append(prefix + [remaining])
            return
        for amount in range(remaining + 1):
            recurse(prefix + [amount], remaining - amount, slots - 1)

    recurse([], units, model_count)
    return np.asarray(weights, dtype=float) * step


def select_validation_weights(validation: pd.DataFrame, model_names: Tuple[str, ...] = COMPONENTS,
                              step: float = WEIGHT_GRID_STEP) -> Dict:
    """Select nonnegative simplex weights minimizing validation MAE only.

    Ties are resolved by lower validation RMSE, then lexicographic weight tuple,
    making selection deterministic. This API intentionally accepts no test data.
    """
    aligned, dropped = _valid_rows(validation, model_names)
    if aligned.empty:
        raise ValueError("No complete validation rows are available for weight selection")
    matrix = aligned[[f"{name}_prediction" for name in model_names]].to_numpy(dtype=float)
    actual = aligned.actual.to_numpy(dtype=float)
    weight_grid = enumerate_weight_grid(len(model_names), step)
    predictions = weight_grid @ matrix.T
    errors = predictions - actual[None, :]
    maes = np.abs(errors).mean(axis=1)
    rmses = np.sqrt(np.square(errors).mean(axis=1))
    selected = min(range(len(weight_grid)), key=lambda i: (maes[i], rmses[i], tuple(weight_grid[i])))
    selected_weights = weight_grid[selected]
    equal_prediction = matrix @ np.full(len(model_names), 1 / len(model_names))
    return {
        "weights": {name: float(weight) for name, weight in zip(model_names, selected_weights)},
        "weight_grid_step": step,
        "objective": "validation MAE; ties by validation RMSE, then lexicographic weights",
        "validation_metrics": {"mae": float(maes[selected]), "rmse": float(rmses[selected]), "n": len(aligned)},
        "equal_weight_validation_metrics": calculate_metrics(actual, equal_prediction),
        "validation_rows_dropped_for_missing_or_nonfinite_predictions": dropped,
        "validation_rows": {"count": len(aligned), "start": str(aligned.target_time.min()), "end": str(aligned.target_time.max())},
    }


def apply_weights(frame: pd.DataFrame, weights: Dict[str, float], model_names: Iterable[str] = COMPONENTS) -> np.ndarray:
    names = tuple(model_names)
    aligned, _ = _valid_rows(frame, names)
    if len(aligned) != len(frame):
        raise ValueError("Cannot produce ensemble predictions when component predictions are missing")
    vector = np.asarray([weights[name] for name in names], dtype=float)
    if np.any(vector < 0) or not np.isclose(vector.sum(), 1.0):
        raise ValueError("Ensemble weights must be nonnegative and sum to one")
    values = aligned[[f"{name}_prediction" for name in names]].to_numpy(dtype=float)
    return values @ vector


def select_weights_and_predict(validation: pd.DataFrame, test: pd.DataFrame,
                               model_names: Tuple[str, ...] = COMPONENTS,
                               step: float = WEIGHT_GRID_STEP) -> Tuple[Dict, np.ndarray]:
    """Fit weights on validation, then apply those frozen weights to test predictions."""
    selection = select_validation_weights(validation, model_names, step)
    return selection, apply_weights(test, selection["weights"], model_names)


def _read_test_predictions(label: str, transformer_dir: Path, baseline_dir: Path) -> pd.DataFrame:
    transformer = pd.read_csv(transformer_dir / label / "test_predictions.csv", parse_dates=["target_time"])
    baseline = pd.read_csv(baseline_dir / label / "test_predictions.csv", parse_dates=["target_time"])
    if _keys(transformer) != _keys(baseline):
        raise ValueError(f"Stage 2 and Stage 3 test populations differ for {label}")
    expected = [f"{name}_prediction" for name in ALL_MODELS]
    if any(col not in transformer.columns for col in expected):
        raise ValueError(f"Stage 3 test predictions do not include every eligible model for {label}")
    return transformer[["series", "target_time", "actual", *expected]].copy()


def _validation_predictions(grid: pd.DataFrame, label: str, steps: int, selected_hgb_name: str,
                            config: TransformerConfig) -> Tuple[pd.DataFrame, Dict]:
    rows = supervised(grid, RESEARCH, steps)
    train, validation, test, splits = chronological_split(rows, RESEARCH)
    if train.empty or validation.empty or test.empty:
        raise ValueError(f"{label} does not have nonempty chronological train, validation, and test splits")
    columns = feature_columns(rows)
    train_table = historical_average_table(train, RESEARCH)
    x_train = model_matrix(train, columns, train_table, RESEARCH)
    x_validation = model_matrix(validation, columns, train_table, RESEARCH)
    available = {candidate.name: candidate for candidate in candidates()}
    if "ridge" not in available or selected_hgb_name not in available:
        raise RuntimeError(f"Required base candidate is not configured: {selected_hgb_name}")
    predicted = {}
    for key, name in (("ridge", "ridge"), ("histogram_gradient_boosting", selected_hgb_name)):
        model = available[name].factory()
        model.fit(x_train, train.target)
        predicted[key] = np.clip(model.predict(x_validation), *RESEARCH.clip)

    train_sequences = build_sequences(grid, train, config.sequence_length)
    validation_sequences = build_sequences(grid, validation, config.sequence_length)
    test_sequences = build_sequences(grid, test, config.sequence_length)
    transformer = fit_transformer(train_sequences, train.target.to_numpy(), validation_sequences,
                                  validation.target.to_numpy(), config)
    predicted["transformer"] = np.clip(transformer.predict(validation_sequences), *RESEARCH.clip)
    validation_frame = pd.DataFrame({"series": validation.series.astype(str).to_numpy(),
                                     "target_time": pd.to_datetime(validation.target_time, utc=True).to_numpy(),
                                     "actual": validation.target.to_numpy(dtype=float)})
    for key, values in predicted.items():
        validation_frame[f"{key}_prediction"] = values
    transformer_test = pd.DataFrame({"series": test.series.astype(str).to_numpy(),
                                     "target_time": pd.to_datetime(test.target_time, utc=True).to_numpy(),
                                     "transformer_prediction": np.clip(transformer.predict(test_sequences), *RESEARCH.clip)})
    info = {"splits": splits, "transformer_training": transformer.history,
            "training_rows_for_base_models": len(train), "validation_rows": len(validation),
            "transformer_test_predictions_reproduced": transformer_test}
    return validation_frame, info


def run_ensemble_evaluation(dataset_path: Path | None = None,
                            output_dir: Path | None = None,
                            config: TransformerConfig = TransformerConfig()) -> Dict:
    settings = get_settings()
    dataset_path = dataset_path or settings.dataset_path
    root = Path(__file__).resolve().parent
    stage2_dir = root / "statistical"
    stage3_dir = root / "transformer"
    output_dir = output_dir or root / "ensemble"
    baseline_report = run_research_evaluation(dataset_path=dataset_path, output_dir=stage2_dir)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "status": baseline_report["status"],
              "dataset": str(dataset_path), "target": RESEARCH.target,
              "selection_policy": "weighted-average weights selected by validation MAE only; held-out test used once for reporting",
              "transformer_training_configuration": asdict(config),
              "components": list(COMPONENTS), "weight_grid_step": WEIGHT_GRID_STEP,
              "data_validation": baseline_report.get("data_validation"), "coverage": baseline_report.get("coverage"),
              "horizons": {}, "limitations": [
                  "The public daily dataset has undocumented provenance and incomplete series/date coverage.",
                  "The small validation interval may make selected weights unstable; test data is not used to select them.",
                  "Transformer validation predictions use a model whose checkpoint was selected by validation early stopping; this may make validation-based meta-weights optimistic, while the test period remains held out.",
                  "Ridge and Gradient Boosting validation predictions are trained on the train split; Stage 3 test predictions use the existing train-plus-validation refit protocol, so fitted populations differ.",
                  "Results describe this public dataset only and do not validate live traffic or activate routing forecasts.",
              ]}
    output_dir.mkdir(parents=True, exist_ok=True)
    if baseline_report["status"] != "evaluated":
        report["reason"] = baseline_report.get("reason", "Insufficient data for chronological evaluation")
        (output_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        return report

    data, _ = load_research(dataset_path)
    grid = to_grid(data, RESEARCH)
    for label, steps in RESEARCH.horizons.items():
        stage2_horizon = baseline_report["horizons"][label]
        hgb_name = stage2_horizon["selected_gradient_boosting_configuration_on_validation"]
        validation, split_info = _validation_predictions(grid, label, steps, hgb_name, config)
        validation, validation_drop = _valid_rows(validation, COMPONENTS)
        if len(validation) < 2:
            raise ValueError(f"Insufficient complete validation predictions for {label}")
        test_raw = _read_test_predictions(label, stage3_dir, stage2_dir)
        reproduced = split_info["transformer_test_predictions_reproduced"].copy()
        persisted_transformer = test_raw[["series", "target_time", "transformer_prediction"]].copy()
        persisted_transformer["series"] = persisted_transformer.series.astype(str)
        persisted_transformer["target_time"] = pd.to_datetime(persisted_transformer.target_time, utc=True)
        reproduced["series"] = reproduced.series.astype(str)
        reproduced["target_time"] = pd.to_datetime(reproduced.target_time, utc=True)
        if _keys(reproduced) != _keys(persisted_transformer):
            raise ValueError(f"Reproduced Transformer and Stage 3 test rows differ for {label}")
        check = persisted_transformer.merge(reproduced, on=["series", "target_time"], suffixes=("_saved", "_reproduced"),
                                            validate="one_to_one")
        if not np.allclose(check.transformer_prediction_saved, check.transformer_prediction_reproduced, rtol=1e-5, atol=1e-5):
            raise ValueError(f"Reproduced Transformer test predictions do not match Stage 3 outputs for {label}")
        test, test_drop = _valid_rows(test_raw, ALL_MODELS)
        if test.empty:
            raise ValueError(f"No complete common test predictions are available for {label}")
        selected, weighted_predictions = select_weights_and_predict(validation, test, COMPONENTS, WEIGHT_GRID_STEP)
        test["weighted_ensemble_prediction"] = weighted_predictions
        equal_weights = {name: 1 / len(COMPONENTS) for name in COMPONENTS}
        test["equal_weight_ensemble_prediction"] = apply_weights(test, equal_weights)
        metrics_rows = []
        for name in ALL_MODELS + ("equal_weight_ensemble", "weighted_ensemble"):
            metrics_rows.append({"model": name, **calculate_metrics(test.actual, test[f"{name}_prediction"])})
        metrics_frame = pd.DataFrame(metrics_rows)
        test_population = {"n_rows_per_model": len(test), "unique_test_timestamps": int(test.target_time.nunique()),
                          "start": str(test.target_time.min()), "end": str(test.target_time.max()),
                          "target_definition": RESEARCH.target}
        horizon_report = {
            "selection": selected,
            "equal_weight_comparator": {"weights": {name: 1 / len(COMPONENTS) for name in COMPONENTS},
                                         "selected_using_test": False},
            "test_population": test_population,
            "test_rows_dropped_for_missing_or_nonfinite_predictions": test_drop,
            "validation_rows_dropped_for_missing_or_nonfinite_predictions": validation_drop,
            "test_metrics": metrics_frame.to_dict(orient="records"),
            "chronological_splits": split_info["splits"],
            "validation_training": split_info["transformer_training"],
            "training_rows_for_base_models": split_info["training_rows_for_base_models"],
            "saved_transformer_test_predictions_reproduced": True,
            "gradient_boosting_configuration": hgb_name,
        }
        horizon_dir = output_dir / label
        horizon_dir.mkdir(parents=True, exist_ok=True)
        validation.assign(**{f"{key}_residual": validation[f"{key}_prediction"] - validation.actual for key in COMPONENTS}).to_csv(
            horizon_dir / "validation_predictions.csv", index=False)
        test.to_csv(horizon_dir / "test_predictions.csv", index=False)
        metrics_frame.to_csv(horizon_dir / "test_metrics.csv", index=False)
        (horizon_dir / "summary.json").write_text(json.dumps(horizon_report, indent=2, allow_nan=False), encoding="utf-8")
        report["horizons"][label] = horizon_report
    report["status"] = "evaluated"
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    report = run_ensemble_evaluation()
    print(json.dumps({"status": report["status"],
                      "horizons": {h: {row["model"]: row["mae"] for row in values["test_metrics"]}
                                  for h, values in report.get("horizons", {}).items()}}, indent=2))


if __name__ == "__main__":
    main()
