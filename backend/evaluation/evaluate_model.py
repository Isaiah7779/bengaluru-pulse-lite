"""
Bengaluru Pulse - ML Model Evaluation

Evaluates the trained Random Forest congestion prediction model
using the same preprocessing pipeline used during training.

Metrics:
- MAE
- RMSE
- R2 Score
- Explained Variance

Also generates:
- Actual vs Predicted CSV
- Feature importance CSV
- Evaluation summary JSON
"""

from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    explained_variance_score,
)
from sklearn.model_selection import train_test_split


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATASET_PATH = BASE_DIR / "traffic_dataset.csv"
MODEL_PATH = BASE_DIR / "traffic_model.pkl"

AREA_ENCODER_PATH = BASE_DIR / "area_encoder.pkl"
ROAD_ENCODER_PATH = BASE_DIR / "road_encoder.pkl"
WEATHER_ENCODER_PATH = BASE_DIR / "weather_encoder.pkl"

OUTPUT_DIR = Path(__file__).resolve().parent

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# FEATURES
# ============================================================

FEATURE_COLUMNS = [
    "Area Name",
    "Road/Intersection Name",
    "Traffic Volume",
    "Average Speed",
    "Weather Conditions",
]

TARGET_COLUMN = "Congestion Level"


# ============================================================
# LOAD DATASET
# ============================================================

def load_dataset():

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found: {DATASET_PATH}"
        )

    dataframe = pd.read_csv(DATASET_PATH)

    required_columns = FEATURE_COLUMNS + [
        TARGET_COLUMN
    ]

    missing = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"Dataset is missing columns: {missing}"
        )

    dataframe = dataframe[
        required_columns
    ].dropna()

    return dataframe


# ============================================================
# ENCODE DATA
# ============================================================

def encode_features(dataframe):

    area_encoder = joblib.load(
        AREA_ENCODER_PATH
    )

    road_encoder = joblib.load(
        ROAD_ENCODER_PATH
    )

    weather_encoder = joblib.load(
        WEATHER_ENCODER_PATH
    )

    encoded = dataframe.copy()

    encoded["Area Name"] = area_encoder.transform(
        encoded["Area Name"]
    )

    encoded["Road/Intersection Name"] = road_encoder.transform(
        encoded["Road/Intersection Name"]
    )

    encoded["Weather Conditions"] = weather_encoder.transform(
        encoded["Weather Conditions"]
    )

    return encoded


# ============================================================
# MAIN EVALUATION
# ============================================================

def evaluate_model():

    print("=" * 60)
    print("BENGALURU PULSE - MODEL EVALUATION")
    print("=" * 60)

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    dataframe = load_dataset()

    print(
        f"\nDataset records: {len(dataframe)}"
    )

    # --------------------------------------------------------
    # Encode
    # --------------------------------------------------------

    encoded = encode_features(
        dataframe
    )

    X = encoded[
        FEATURE_COLUMNS
    ]

    y = encoded[
        TARGET_COLUMN
    ]

    # --------------------------------------------------------
    # Same split used during training
    # --------------------------------------------------------

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
    )

    print(
        f"Training samples: {len(X_train)}"
    )

    print(
        f"Testing samples: {len(X_test)}"
    )

    # --------------------------------------------------------
    # Load trained model
    # --------------------------------------------------------

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}"
        )

    model = joblib.load(
        MODEL_PATH
    )

    # --------------------------------------------------------
    # Predictions
    # --------------------------------------------------------

    predictions = model.predict(
        X_test
    )

    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    mae = mean_absolute_error(
        y_test,
        predictions,
    )

    rmse = np.sqrt(
        mean_squared_error(
            y_test,
            predictions,
        )
    )

    r2 = r2_score(
        y_test,
        predictions,
    )

    explained_variance = explained_variance_score(
        y_test,
        predictions,
    )

    # --------------------------------------------------------
    # Print results
    # --------------------------------------------------------

    print("\nMODEL PERFORMANCE")
    print("-" * 40)

    print(
        f"MAE                 : {mae:.4f}"
    )

    print(
        f"RMSE                : {rmse:.4f}"
    )

    print(
        f"R2 Score            : {r2:.4f}"
    )

    print(
        f"Explained Variance  : {explained_variance:.4f}"
    )

    # --------------------------------------------------------
    # Actual vs predicted
    # --------------------------------------------------------

    results = pd.DataFrame(
        {
            "Actual Congestion": y_test.values,
            "Predicted Congestion": predictions,
            "Absolute Error": np.abs(
                y_test.values - predictions
            ),
        }
    )

    results_path = (
        OUTPUT_DIR /
        "actual_vs_predicted.csv"
    )

    results.to_csv(
        results_path,
        index=False,
    )

    # --------------------------------------------------------
    # Feature importance
    # --------------------------------------------------------

    if hasattr(
        model,
        "feature_importances_",
    ):

        importance = pd.DataFrame(
            {
                "Feature": FEATURE_COLUMNS,
                "Importance": model.feature_importances_,
            }
        ).sort_values(
            "Importance",
            ascending=False,
        )

        importance_path = (
            OUTPUT_DIR /
            "feature_importance.csv"
        )

        importance.to_csv(
            importance_path,
            index=False,
        )

        print("\nFEATURE IMPORTANCE")
        print("-" * 40)

        for _, row in importance.iterrows():

            print(
                f"{row['Feature']}: "
                f"{row['Importance']:.4f}"
            )

    # --------------------------------------------------------
    # Save metrics
    # --------------------------------------------------------

    metrics = {
        "model": "RandomForestRegressor",
        "dataset_records": int(len(dataframe)),
        "training_samples": int(len(X_train)),
        "testing_samples": int(len(X_test)),
        "test_size": 0.20,
        "random_state": 42,
        "mae": round(float(mae), 6),
        "rmse": round(float(rmse), 6),
        "r2_score": round(float(r2), 6),
        "explained_variance": round(
            float(explained_variance),
            6,
        ),
    }

    metrics_path = (
        OUTPUT_DIR /
        "evaluation_metrics.json"
    )

    with open(
        metrics_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metrics,
            file,
            indent=4,
        )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print("\nFILES GENERATED")
    print("-" * 40)

    print(
        f"Metrics          : {metrics_path}"
    )

    print(
        f"Predictions      : {results_path}"
    )

    if hasattr(
        model,
        "feature_importances_",
    ):

        print(
            f"Feature importance: {importance_path}"
        )

    print("\nEvaluation completed successfully.")

    print("=" * 60)


if __name__ == "__main__":
    evaluate_model()