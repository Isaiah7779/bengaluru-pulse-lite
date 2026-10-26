"""Research-only Transformer experiment for chronological congestion forecasting.

This module is never imported by the routing predictor or model registry. Run from
``backend`` with ``python -m forecasting.transformer_experiment`` after installing
the pinned optional research dependency (PyTorch).

Each sample is a 28-step history ending at the forecast origin. Per-step features,
in order, are congestion value (causal forward/backfill), observed-value indicator,
day-of-week sine/cosine, and annual day sine/cosine. The scalar target is congestion
at ``origin + horizon`` (1 day or 7 days), exactly as in the V2 research evaluator.
The imputer/scaler and target scaler are fit on chronological training rows only.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from core.settings import get_settings
from evaluation.v2.statistical_evaluation import calculate_metrics, run_research_evaluation
from forecasting.pipeline import RESEARCH, chronological_split, load_research, supervised, to_grid

FEATURE_ORDER = (
    "congestion_value",
    "observed_value_indicator",
    "day_of_week_sin",
    "day_of_week_cos",
    "annual_day_sin",
    "annual_day_cos",
)
MODEL_NAMES = ("persistence", "seasonal_naive", "historical_average", "ridge", "histogram_gradient_boosting")


@dataclass(frozen=True)
class TransformerConfig:
    sequence_length: int = 28
    input_size: int = len(FEATURE_ORDER)
    d_model: int = 32
    nhead: int = 4
    num_layers: int = 2
    dim_feedforward: int = 64
    dropout: float = 0.10
    learning_rate: float = 0.001
    weight_decay: float = 0.0001
    batch_size: int = 256
    max_epochs: int = 32
    patience: int = 5
    min_delta: float = 0.0001
    seed: int = 42
    min_train_samples: int = 128
    device: str = "cpu"


class InsufficientDataError(ValueError):
    """Raised when a chronological split cannot support model fitting/evaluation."""


class TransformerRegressor(nn.Module):
    """Encoder-only Transformer mapping a historical sequence to one scalar target."""

    def __init__(self, config: TransformerConfig):
        super().__init__()
        if config.d_model % config.nhead:
            raise ValueError("d_model must be divisible by nhead")
        self.config = config
        self.input_projection = nn.Linear(config.input_size, config.d_model)
        self.register_buffer("position_encoding", self._position_encoding(config.sequence_length, config.d_model), persistent=True)
        layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.nhead,
            dim_feedforward=config.dim_feedforward,
            dropout=config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=config.num_layers, enable_nested_tensor=False)
        self.regression_head = nn.Sequential(nn.LayerNorm(config.d_model), nn.Linear(config.d_model, 1))
        self._initialize_parameters()

    @staticmethod
    def _position_encoding(length: int, width: int) -> torch.Tensor:
        position = torch.arange(length, dtype=torch.float32).unsqueeze(1)
        scale = torch.exp(torch.arange(0, width, 2, dtype=torch.float32) * (-np.log(10000.0) / width))
        encoding = torch.zeros(length, width, dtype=torch.float32)
        encoding[:, 0::2] = torch.sin(position * scale)
        if width > 1:
            encoding[:, 1::2] = torch.cos(position * scale[:encoding[:, 1::2].shape[1]])
        return encoding.unsqueeze(0)

    def _initialize_parameters(self) -> None:
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.MultiheadAttention):
                nn.init.xavier_uniform_(module.in_proj_weight)
                if module.in_proj_bias is not None:
                    nn.init.zeros_(module.in_proj_bias)
            elif isinstance(module, nn.LayerNorm):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)

    def forward(self, sequences: torch.Tensor) -> torch.Tensor:
        if sequences.ndim != 3:
            raise ValueError("Expected input tensor shape (batch, sequence, features)")
        if sequences.shape[1] != self.config.sequence_length or sequences.shape[2] != self.config.input_size:
            raise ValueError(f"Expected trailing tensor shape ({self.config.sequence_length}, {self.config.input_size})")
        encoded = self.input_projection(sequences) + self.position_encoding
        encoded = self.encoder(encoded)
        return self.regression_head(encoded[:, -1, :]).squeeze(-1)


def build_sequences(grid: pd.DataFrame, samples: pd.DataFrame, sequence_length: int = 28) -> np.ndarray:
    """Build causal fixed-length feature windows aligned one-for-one with samples."""
    if samples.empty:
        return np.empty((0, sequence_length, len(FEATURE_ORDER)), dtype=np.float32)
    indexed = {sid: group.set_index("time")[RESEARCH.target].sort_index() for sid, group in grid.groupby("series")}
    windows = []
    for row in samples.itertuples(index=False):
        origin = pd.Timestamp(row.origin)
        times = pd.date_range(end=origin, periods=sequence_length, freq=RESEARCH.freq)
        series = indexed[row.series]
        raw = series.reindex(times)
        # Forward fill uses only observations at/before the origin. Backfill only
        # fills the left edge from the first historical observation in this window.
        values = raw.ffill().bfill().fillna(0.0).to_numpy(dtype=np.float32)
        present = raw.notna().to_numpy(dtype=np.float32)
        dow = times.dayofweek.to_numpy(dtype=np.float32)
        doy = times.dayofyear.to_numpy(dtype=np.float32)
        dow_angle = 2 * np.pi * dow / 7.0
        year_angle = 2 * np.pi * (doy - 1) / 365.25
        windows.append(np.column_stack((values, present, np.sin(dow_angle), np.cos(dow_angle),
                                        np.sin(year_angle), np.cos(year_angle))))
    result = np.asarray(windows, dtype=np.float32)
    if result.shape != (len(samples), sequence_length, len(FEATURE_ORDER)):
        raise RuntimeError(f"Sequence construction shape mismatch: {result.shape}")
    return result


@dataclass
class FittedTransformer:
    model: TransformerRegressor
    feature_scaler: StandardScaler
    target_scaler: StandardScaler
    history: Dict
    config: TransformerConfig

    def predict(self, sequences: np.ndarray, batch_size: Optional[int] = None) -> np.ndarray:
        if len(sequences) == 0:
            return np.empty(0, dtype=float)
        transformed = self._transform(sequences)
        self.model.eval()
        device = torch.device(self.config.device)
        outputs = []
        with torch.inference_mode():
            for start in range(0, len(transformed), batch_size or self.config.batch_size):
                tensor = torch.as_tensor(transformed[start:start+(batch_size or self.config.batch_size)], dtype=torch.float32, device=device)
                outputs.append(self.model(tensor).detach().cpu().numpy())
        scaled = np.concatenate(outputs).reshape(-1, 1)
        return self.target_scaler.inverse_transform(scaled).reshape(-1)

    def _transform(self, sequences: np.ndarray) -> np.ndarray:
        shape = sequences.shape
        return self.feature_scaler.transform(sequences.reshape(-1, shape[-1])).reshape(shape).astype(np.float32)


def fit_transformer(train_x: np.ndarray, train_y: np.ndarray, validation_x: np.ndarray,
                    validation_y: np.ndarray, config: TransformerConfig = TransformerConfig()) -> FittedTransformer:
    """Fit scalers and Transformer on training data; validation controls early stopping."""
    if train_x.ndim != 3 or validation_x.ndim != 3:
        raise ValueError("Sequence arrays must have shape (samples, sequence, features)")
    expected_shape = (config.sequence_length, config.input_size)
    if train_x.shape[1:] != expected_shape or validation_x.shape[1:] != expected_shape:
        raise ValueError(f"Input sequences must have shape (n, {expected_shape[0]}, {expected_shape[1]})")
    train_y = np.asarray(train_y, dtype=np.float32).reshape(-1)
    validation_y = np.asarray(validation_y, dtype=np.float32).reshape(-1)
    if len(train_x) != len(train_y) or len(validation_x) != len(validation_y):
        raise ValueError("Sequence and target row counts must match")
    if len(train_x) < config.min_train_samples:
        raise InsufficientDataError(f"Need at least {config.min_train_samples} training windows; received {len(train_x)}")
    if not len(validation_x):
        raise InsufficientDataError("At least one chronological validation window is required for early stopping")
    if not np.isfinite(train_x).all() or not np.isfinite(validation_x).all() or not np.isfinite(train_y).all() or not np.isfinite(validation_y).all():
        raise ValueError("Transformer inputs and targets must be finite after Stage 1 preprocessing")

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    previous_deterministic = torch.are_deterministic_algorithms_enabled()
    previous_threads = torch.get_num_threads()
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    try:
        feature_scaler = StandardScaler().fit(train_x.reshape(-1, config.input_size))
        train_scaled = feature_scaler.transform(train_x.reshape(-1, config.input_size)).reshape(train_x.shape).astype(np.float32)
        validation_scaled = feature_scaler.transform(validation_x.reshape(-1, config.input_size)).reshape(validation_x.shape).astype(np.float32)
        target_scaler = StandardScaler().fit(train_y.reshape(-1, 1))
        train_target = target_scaler.transform(train_y.reshape(-1, 1)).reshape(-1).astype(np.float32)
        validation_target = target_scaler.transform(validation_y.reshape(-1, 1)).reshape(-1).astype(np.float32)

        device = torch.device(config.device)
        model = TransformerRegressor(config).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
        loss_fn = nn.MSELoss()
        generator = torch.Generator().manual_seed(config.seed)
        training_loader = DataLoader(
            TensorDataset(torch.from_numpy(train_scaled), torch.from_numpy(train_target)),
            batch_size=config.batch_size, shuffle=True, generator=generator, num_workers=0,
        )
        validation_tensor = torch.from_numpy(validation_scaled).to(device)
        validation_target_tensor = torch.from_numpy(validation_target).to(device)
        best_loss = float("inf")
        best_epoch = 0
        best_weights = None
        stale_epochs = 0
        train_losses, validation_losses = [], []
        for epoch in range(1, config.max_epochs + 1):
            model.train()
            total, count = 0.0, 0
            for batch_x, batch_y in training_loader:
                batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                optimizer.zero_grad(set_to_none=True)
                prediction = model(batch_x)
                loss = loss_fn(prediction, batch_y)
                loss.backward()
                optimizer.step()
                total += float(loss.detach()) * len(batch_x)
                count += len(batch_x)
            train_loss = total / count
            model.eval()
            with torch.inference_mode():
                val_loss = float(loss_fn(model(validation_tensor), validation_target_tensor))
            train_losses.append(train_loss)
            validation_losses.append(val_loss)
            if val_loss < best_loss - config.min_delta:
                best_loss = val_loss
                best_epoch = epoch
                best_weights = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                stale_epochs = 0
            else:
                stale_epochs += 1
                if stale_epochs >= config.patience:
                    break
        if best_weights is None:
            raise RuntimeError("Training did not produce a finite validation checkpoint")
        model.load_state_dict(best_weights)
        history = {
            "epochs_completed": len(train_losses), "best_epoch": best_epoch,
            "best_validation_mse_scaled": best_loss, "stopped_early": len(train_losses) < config.max_epochs,
            "training_mse_scaled_by_epoch": train_losses, "validation_mse_scaled_by_epoch": validation_losses,
        }
        return FittedTransformer(model, feature_scaler, target_scaler, history, config)
    finally:
        torch.set_num_threads(previous_threads)
        torch.use_deterministic_algorithms(previous_deterministic)


def align_baseline_predictions(baselines: pd.DataFrame, transformer: pd.DataFrame) -> pd.DataFrame:
    """Join predictions only when the full eligible (series, target_time) key sets match."""
    keys = ["series", "target_time"]
    if baselines.duplicated(keys).any() or transformer.duplicated(keys).any():
        raise ValueError("Evaluation rows contain duplicate (series, target_time) keys")
    left_keys = set(zip(baselines.series.astype(str), pd.to_datetime(baselines.target_time, utc=True)))
    right_keys = set(zip(transformer.series.astype(str), pd.to_datetime(transformer.target_time, utc=True)))
    if left_keys != right_keys or len(baselines) != len(transformer):
        raise ValueError("Transformer and baseline evaluations do not use identical eligible test rows")
    merged = baselines.merge(transformer[keys + ["transformer_prediction"]], on=keys, how="inner", validate="one_to_one")
    merged["transformer_residual"] = merged.transformer_prediction - merged.actual
    return merged


def _comparison_rows(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in MODEL_NAMES + ("transformer",):
        rows.append({"model": name, **calculate_metrics(frame.actual, frame[f"{name}_prediction"])})
    return pd.DataFrame(rows)


def run_transformer_experiment(dataset_path: Optional[Path] = None,
                               output_dir: Optional[Path] = None,
                               config: TransformerConfig = TransformerConfig()) -> Dict:
    """Run alongside the Stage 2 research evaluation; never registers/activates models."""
    eval_root = Path(__file__).resolve().parents[1] / "evaluation" / "v2" / "statistical"
    baseline_report = run_research_evaluation(dataset_path=dataset_path, output_dir=eval_root)
    output_dir = output_dir or Path(__file__).resolve().parents[1] / "evaluation" / "v2" / "transformer"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": baseline_report["status"],
        "target": RESEARCH.target,
        "target_definition": "congestion at forecast origin + configured horizon (same as Stage 2)",
        "input_sequence": {"length_steps": config.sequence_length, "frequency": RESEARCH.freq,
                           "includes_forecast_origin": True, "feature_order": list(FEATURE_ORDER)},
        "preprocessing": {"input_scaler": "StandardScaler fitted on training windows only",
                          "target_scaler": "StandardScaler fitted on training targets only",
                          "missing_history": "causal forward-fill; left padding uses earliest observation available at the origin; observation indicator retained"},
        "training_configuration": asdict(config) | {"optimizer": "AdamW", "loss": "Mean Squared Error", "early_stopping": "validation scaled MSE; patience/min_delta; restore best validation checkpoint"},
        "data_validation": baseline_report.get("data_validation"),
        "coverage": baseline_report.get("coverage"),
        "horizons": {},
        "limitations": [
            "The public daily dataset has undocumented provenance and incomplete series/date coverage.",
            "A Transformer is an experiment; the short history and weak measured temporal structure may not support its added capacity.",
            "Results apply only to this dataset and chronological holdout, not live road traffic.",
        ],
    }
    if baseline_report["status"] != "evaluated":
        report["reason"] = baseline_report.get("reason", "Insufficient data for chronological baseline evaluation")
        (output_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        return report

    data, _ = load_research(dataset_path or get_settings().dataset_path)
    grid = to_grid(data, RESEARCH)
    for label, steps in RESEARCH.horizons.items():
        horizon_dir = output_dir / label
        base_dir = eval_root / label
        reference = pd.read_csv(base_dir / "test_predictions.csv", parse_dates=["target_time"])
        supervised_rows = supervised(grid, RESEARCH, steps)
        train, validation, test, splits = chronological_split(supervised_rows, RESEARCH)
        if len(test) != len(reference) or test.empty or train.empty or validation.empty:
            raise InsufficientDataError(f"{label}: chronological eligible rows do not match the Stage 2 evaluation")
        train_x = build_sequences(grid, train, config.sequence_length)
        validation_x = build_sequences(grid, validation, config.sequence_length)
        test_x = build_sequences(grid, test, config.sequence_length)
        fitted = fit_transformer(train_x, train.target.to_numpy(), validation_x, validation.target.to_numpy(), config)
        transformer_rows = pd.DataFrame({"series": test.series.astype(str).to_numpy(),
                                         "target_time": pd.to_datetime(test.target_time, utc=True).to_numpy(),
                                         "transformer_prediction": np.clip(fitted.predict(test_x), *RESEARCH.clip)})
        reference["series"] = reference.series.astype(str)
        reference["target_time"] = pd.to_datetime(reference.target_time, utc=True)
        transformer_rows["target_time"] = pd.to_datetime(transformer_rows.target_time, utc=True)
        combined = align_baseline_predictions(reference, transformer_rows)
        comparison = _comparison_rows(combined)
        horizon_report = {
            "population": {"n_rows_per_model": len(combined), "unique_test_timestamps": int(combined.target_time.nunique()),
                           "start": str(combined.target_time.min()), "end": str(combined.target_time.max()),
                           "target_definition": RESEARCH.target},
            "metrics": comparison.to_dict(orient="records"),
            "selected_gradient_boosting_configuration_on_validation": baseline_report["horizons"][label]["selected_gradient_boosting_configuration_on_validation"],
            "chronological_splits": splits,
            "training": fitted.history,
            "training_samples": {"train": int(len(train)), "validation": int(len(validation)), "test": int(len(test))},
        }
        horizon_dir.mkdir(parents=True, exist_ok=True)
        combined.to_csv(horizon_dir / "test_predictions.csv", index=False)
        comparison.to_csv(horizon_dir / "model_comparison.csv", index=False)
        (horizon_dir / "summary.json").write_text(json.dumps(horizon_report, indent=2, allow_nan=False), encoding="utf-8")
        report["horizons"][label] = horizon_report
    report["status"] = "evaluated"
    (output_dir / "summary.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def main() -> None:
    report = run_transformer_experiment()
    result = {"status": report["status"], "horizons": {h: {row["model"]: row["mae"] for row in val.get("metrics", [])}
                                                         for h, val in report.get("horizons", {}).items()}}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
