"""Unit tests only; the tiny fixtures below are never reported as research evidence."""

import numpy as np
import pandas as pd
import pytest

from evaluation.v2.ensemble_evaluation import (
    COMPONENTS,
    align_prediction_frames,
    apply_weights,
    select_validation_weights,
    select_weights_and_predict,
)


def make_predictions(actual, ridge, hgb, transformer):
    n = len(actual)
    return pd.DataFrame({
        "series": ["Road A"] * n,
        "target_time": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
        "actual": actual,
        "ridge_prediction": ridge,
        "histogram_gradient_boosting_prediction": hgb,
        "transformer_prediction": transformer,
    })


def test_validation_weight_selection_uses_simplex_and_known_validation_optimum():
    actual = np.array([0.0, 10.0, 20.0, 30.0])
    validation = make_predictions(actual, actual + 2, actual, 30 - actual)
    selection = select_validation_weights(validation, COMPONENTS, step=0.25)
    assert selection["weights"] == {"ridge": 0.0, "histogram_gradient_boosting": 1.0, "transformer": 0.0}
    assert selection["validation_metrics"]["mae"] == pytest.approx(0.0)
    assert selection["validation_metrics"]["n"] == len(actual)
    assert sum(selection["weights"].values()) == pytest.approx(1.0)


def test_missing_predictions_are_excluded_and_reported_without_imputation():
    validation = make_predictions([0, 10, 20], [0, 10, 20], [0, 10, 20], [0, 10, 20])
    validation.loc[1, "transformer_prediction"] = np.nan
    selection = select_validation_weights(validation, COMPONENTS, step=0.5)
    assert selection["validation_metrics"]["n"] == 2
    assert selection["validation_rows_dropped_for_missing_or_nonfinite_predictions"] == 1
    with pytest.raises(ValueError, match="missing"):
        apply_weights(validation, selection["weights"])


def test_prediction_alignment_requires_exact_keys_and_returns_common_rows():
    actual = make_predictions([1, 2], [1, 2], [1, 2], [1, 2])[["series", "target_time", "actual"]]
    frames = {name: pd.DataFrame({"series": actual.series.to_numpy(copy=True), "target_time": actual.target_time.to_numpy(copy=True),
                                  f"{name}_prediction": [1.0, 2.0]}) for name in COMPONENTS}
    aligned, dropped = align_prediction_frames(actual, frames, COMPONENTS)
    assert len(aligned) == 2 and dropped["incomplete_or_nonfinite_rows"] == 0
    complete_transformer = frames["transformer"].copy()
    frames["transformer"] = frames["transformer"].iloc[:1].copy()
    aligned, dropped = align_prediction_frames(actual, frames, COMPONENTS)
    assert len(aligned) == 1 and dropped["missing_prediction_key_rows"] == 1
    frames["transformer"] = complete_transformer
    frames["transformer"].loc[1, "target_time"] += pd.Timedelta(days=1)
    with pytest.raises(ValueError, match="absent from the actual evaluation"):
        align_prediction_frames(actual, frames, COMPONENTS)


def test_weight_selection_is_reproducible():
    validation = make_predictions([1, 2, 3, 4], [1, 2.1, 3, 4.1], [1.2, 2, 3.2, 4], [0.8, 2.2, 3.1, 4.1])
    first = select_validation_weights(validation, COMPONENTS, step=0.1)
    second = select_validation_weights(validation, COMPONENTS, step=0.1)
    assert first["weights"] == second["weights"]
    assert first["validation_metrics"] == second["validation_metrics"]


def test_test_predictions_cannot_change_validation_selected_weights():
    validation = make_predictions([0, 10, 20, 30], [2, 12, 22, 32], [0, 10, 20, 30], [30, 20, 10, 0])
    test = make_predictions([1, 9], [1, 9], [1, 9], [1, 9])
    first_selection, first_prediction = select_weights_and_predict(validation, test, COMPONENTS, step=0.25)
    changed_test = test.copy()
    changed_test["actual"] = [1000, -1000]
    for name in COMPONENTS:
        changed_test[f"{name}_prediction"] = np.arange(len(changed_test)) * 500
    second_selection, second_prediction = select_weights_and_predict(validation, changed_test, COMPONENTS, step=0.25)
    assert first_selection["weights"] == second_selection["weights"]
    assert not np.array_equal(first_prediction, second_prediction)
