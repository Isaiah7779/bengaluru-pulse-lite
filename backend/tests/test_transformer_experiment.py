"""Behavior tests for the Transformer research experiment; no fixture is research evidence."""

import numpy as np
import pandas as pd
import pytest
import torch

from forecasting.transformer_experiment import (
    FEATURE_ORDER,
    InsufficientDataError,
    TransformerConfig,
    TransformerRegressor,
    align_baseline_predictions,
    fit_transformer,
)


def small_config(**changes):
    values = {
        "sequence_length": 8,
        "input_size": len(FEATURE_ORDER),
        "d_model": 8,
        "nhead": 2,
        "num_layers": 1,
        "dim_feedforward": 16,
        "dropout": 0.1,
        "batch_size": 8,
        "max_epochs": 8,
        "patience": 2,
        "min_delta": 1e9,
        "seed": 17,
        "min_train_samples": 8,
    }
    values.update(changes)
    return TransformerConfig(**values)


def test_encoder_tensor_shapes_and_invalid_input():
    model = TransformerRegressor(small_config())
    assert model(torch.zeros(3, 8, len(FEATURE_ORDER))).shape == (3,)
    with pytest.raises(ValueError, match="Expected input tensor shape"):
        model(torch.zeros(3, 8))
    with pytest.raises(ValueError, match="divisible"):
        TransformerRegressor(small_config(d_model=7, nhead=2))


def test_training_uses_validation_early_stopping_and_returns_predictions():
    rng = np.random.default_rng(2)
    train_x = rng.normal(size=(24, 8, len(FEATURE_ORDER))).astype(np.float32)
    val_x = rng.normal(size=(8, 8, len(FEATURE_ORDER))).astype(np.float32)
    train_y = train_x[:, -1, 0] * 3 + 10
    val_y = val_x[:, -1, 0] * 3 + 10
    fitted = fit_transformer(train_x, train_y, val_x, val_y, small_config())
    predictions = fitted.predict(val_x)
    assert predictions.shape == (len(val_x),)
    assert np.isfinite(predictions).all()
    assert fitted.history["epochs_completed"] <= 3
    assert fitted.history["best_epoch"] == 1
    assert fitted.history["stopped_early"] is True
    assert fitted.history["best_validation_mse_scaled"] >= 0


def test_seed_reproduces_transformer_fit_and_predictions():
    rng = np.random.default_rng(9)
    train_x = rng.normal(size=(12, 8, len(FEATURE_ORDER))).astype(np.float32)
    val_x = rng.normal(size=(4, 8, len(FEATURE_ORDER))).astype(np.float32)
    train_y = rng.normal(size=12)
    val_y = rng.normal(size=4)
    config = small_config(max_epochs=2, patience=2, min_delta=0.0)
    first = fit_transformer(train_x, train_y, val_x, val_y, config).predict(val_x)
    second = fit_transformer(train_x, train_y, val_x, val_y, config).predict(val_x)
    np.testing.assert_array_equal(first, second)


def test_feature_and_target_scalers_are_fitted_on_training_only():
    rng = np.random.default_rng(21)
    train_x = rng.normal(size=(10, 8, len(FEATURE_ORDER))).astype(np.float32)
    train_y = rng.normal(size=10)
    val_x = np.full((4, 8, len(FEATURE_ORDER)), 1e6, dtype=np.float32)
    val_y = np.full(4, -1e6)
    fitted = fit_transformer(train_x, train_y, val_x, val_y, small_config(max_epochs=1, patience=1))
    assert fitted.feature_scaler.mean_ == pytest.approx(train_x.reshape(-1, len(FEATURE_ORDER)).mean(axis=0))
    assert fitted.target_scaler.mean_[0] == pytest.approx(train_y.mean())


def test_insufficient_training_windows_are_rejected():
    config = small_config(min_train_samples=10)
    x = np.zeros((4, 8, len(FEATURE_ORDER)), dtype=np.float32)
    with pytest.raises(InsufficientDataError, match="at least 10 training windows"):
        fit_transformer(x, np.zeros(4), x, np.zeros(4), config)


def test_transformer_comparison_requires_identical_test_keys():
    base = pd.DataFrame({
        "series": ["A", "A"], "target_time": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
        "actual": [10.0, 12.0], "ridge_prediction": [11.0, 12.0],
    })
    transformer = pd.DataFrame({
        "series": ["A", "A"], "target_time": pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
        "transformer_prediction": [10.5, 11.5],
    })
    joined = align_baseline_predictions(base, transformer)
    assert len(joined) == 2
    assert joined["transformer_residual"].tolist() == pytest.approx([0.5, -0.5])
    with pytest.raises(ValueError, match="identical eligible test rows"):
        align_baseline_predictions(base, transformer.iloc[:1])
