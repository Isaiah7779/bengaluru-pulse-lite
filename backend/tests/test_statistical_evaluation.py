"""Unit tests for metric and artifact writers; fixtures are not research evidence."""

import json
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import pytest

from evaluation.v2.statistical_evaluation import calculate_metrics, write_horizon_outputs


def test_calculate_metrics_and_undefined_r_squared():
    measured = calculate_metrics([1, 2, 3], [1, 2, 4])
    assert measured["mae"] == pytest.approx(1 / 3)
    assert measured["rmse"] == pytest.approx(np.sqrt(1 / 3))
    assert measured["r2"] == pytest.approx(0.5)
    assert measured["n"] == 3
    assert calculate_metrics([2, 2], [2, 3])["r2"] is None


def test_output_generation_writes_measured_tables_summary_and_svg(tmp_path):
    # This small deterministic fixture tests the writer only; it is never reported as a result.
    n = 32
    actual = np.linspace(10, 40, n)
    predictions = pd.DataFrame({
        "target_time": pd.date_range("2024-02-01", periods=n, freq="D", tz="UTC"),
        "series": ["Area | Road"] * n,
        "actual": actual,
    })
    models = ["persistence", "seasonal_naive", "historical_average", "ridge", "histogram_gradient_boosting"]
    for offset, name in enumerate(models):
        predictions[f"{name}_prediction"] = actual + offset * 0.25
        predictions[f"{name}_residual"] = predictions[f"{name}_prediction"] - actual
    comparison = pd.DataFrame([
        {"model": name, "configuration": "test-only", **calculate_metrics(actual, predictions[f"{name}_prediction"])}
        for name in models
    ])
    z_metadata = {"feature": "last_value", "population": "test rows", "scaler_fit_population": "train + validation",
                  "scaler": "StandardScaler", "n": n, "mean": 0.0, "standard_deviation_population": 1.0}

    summary = write_horizon_outputs(tmp_path, "1d", comparison, predictions, np.linspace(-1, 1, n), z_metadata)

    assert summary["population"]["n_rows_per_model"] == n
    assert all(model["n"] == n for model in summary["models"].values())
    assert summary["error_by_series"]["supported_series"] == 1
    assert summary["z_score"]["scaler_fit_population"] == "train + validation"
    assert pd.read_csv(tmp_path / "model_comparison.csv").shape[0] == 5
    assert pd.read_csv(tmp_path / "test_predictions.csv").shape[0] == n
    assert (tmp_path / "error_by_series.svg").is_file()
    for name in ("model_comparison.svg", "actual_and_predicted_over_time.svg", "residual_distribution.svg",
                 "residuals_over_time.svg", "prediction_vs_actual.svg", "z_score_distribution.svg", "error_by_series.svg"):
        root = ET.parse(tmp_path / name).getroot()
        assert root.tag.endswith("svg")
    written = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert written["models"]["persistence"]["n"] == n
