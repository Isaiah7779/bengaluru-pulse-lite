"""
Bengaluru Pulse - Random Forest Hyperparameter Tuning

Compares the baseline Random Forest model with tuned configurations
using GridSearchCV.

Metrics:
- MAE
- RMSE
- R2 Score
- Explained Variance

The best model is evaluated on a held-out test set and saved as
the final tuned model.
"""

from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    explained_variance_score,
)
from sklearn.model_selection import (
    GridSearchCV,
    train_test_split,
)
from sklearn.preprocessing import LabelEncoder


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATASET_PATH = BASE_DIR / "traffic_dataset.csv"

OUTPUT_DIR = Path(__file__).resolve().parent

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# DATASET CONFIGURATION
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

    dataframe = pd.read_csv(
        DATASET_PATH
    )

    required_columns = (
        FEATURE_COLUMNS
        + [TARGET_COLUMN]
    )

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Dataset missing columns: "
            f"{missing_columns}"
        )

    dataframe = dataframe[
        required_columns
    ].dropna()

    return dataframe


# ============================================================
# ENCODE FEATURES
# ============================================================

def encode_features(dataframe):

    encoded = dataframe.copy()

    area_encoder = LabelEncoder()
    road_encoder = LabelEncoder()
    weather_encoder = LabelEncoder()

    encoded["Area Name"] = (
        area_encoder.fit_transform(
            encoded["Area Name"]
        )
    )

    encoded["Road/Intersection Name"] = (
        road_encoder.fit_transform(
            encoded[
                "Road/Intersection Name"
            ]
        )
    )

    encoded["Weather Conditions"] = (
        weather_encoder.fit_transform(
            encoded[
                "Weather Conditions"
            ]
        )
    )

    return encoded


# ============================================================
# EVALUATION FUNCTION
# ============================================================

def evaluate_model(
    model,
    X_test,
    y_test,
):

    predictions = model.predict(
        X_test
    )

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

    explained_variance = (
        explained_variance_score(
            y_test,
            predictions,
        )
    )

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "r2_score": float(r2),
        "explained_variance": float(
            explained_variance
        ),
    }


# ============================================================
# MAIN
# ============================================================

def tune_model():

    print("=" * 70)
    print(
        "BENGALURU PULSE - "
        "RANDOM FOREST HYPERPARAMETER TUNING"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    dataframe = load_dataset()

    print(
        f"\nDataset records: "
        f"{len(dataframe)}"
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
    # Train/test split
    # --------------------------------------------------------

    X_train, X_test, y_train, y_test = (
        train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=42,
        )
    )

    print(
        f"Training samples: "
        f"{len(X_train)}"
    )

    print(
        f"Testing samples: "
        f"{len(X_test)}"
    )

    # --------------------------------------------------------
    # Baseline model
    # --------------------------------------------------------

    baseline_model = (
        RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        )
    )

    baseline_model.fit(
        X_train,
        y_train,
    )

    baseline_metrics = evaluate_model(
        baseline_model,
        X_test,
        y_test,
    )

    print("\n")
    print(
        "BASELINE RANDOM FOREST"
    )
    print("-" * 50)

    print(
        f"MAE                : "
        f"{baseline_metrics['mae']:.4f}"
    )

    print(
        f"RMSE               : "
        f"{baseline_metrics['rmse']:.4f}"
    )

    print(
        f"R2 Score           : "
        f"{baseline_metrics['r2_score']:.4f}"
    )

    print(
        f"Explained Variance : "
        f"{baseline_metrics['explained_variance']:.4f}"
    )

    # --------------------------------------------------------
    # Hyperparameter grid
    # --------------------------------------------------------

    parameter_grid = {

        "n_estimators": [
            100,
            200,
            300,
        ],

        "max_depth": [
            None,
            10,
            20,
            30,
        ],

        "min_samples_split": [
            2,
            5,
            10,
        ],

        "min_samples_leaf": [
            1,
            2,
            4,
        ],

        "max_features": [
            1.0,
            "sqrt",
        ],
    }

    # --------------------------------------------------------
    # GridSearchCV
    # --------------------------------------------------------

    print("\n")
    print(
        "STARTING HYPERPARAMETER SEARCH"
    )

    print("-" * 50)

    base_estimator = (
        RandomForestRegressor(
            random_state=42,
            n_jobs=-1,
        )
    )

    grid_search = GridSearchCV(
        estimator=base_estimator,
        param_grid=parameter_grid,
        scoring="r2",
        cv=3,
        n_jobs=-1,
        verbose=1,
    )

    grid_search.fit(
        X_train,
        y_train,
    )

    # --------------------------------------------------------
    # Best parameters
    # --------------------------------------------------------

    print("\n")
    print(
        "BEST HYPERPARAMETERS"
    )

    print("-" * 50)

    print(
        json.dumps(
            grid_search.best_params_,
            indent=4,
        )
    )

    print(
        f"\nBest CV R2: "
        f"{grid_search.best_score_:.4f}"
    )

    # --------------------------------------------------------
    # Tuned model
    # --------------------------------------------------------

    tuned_model = (
        grid_search.best_estimator_
    )

    tuned_metrics = evaluate_model(
        tuned_model,
        X_test,
        y_test,
    )

    print("\n")
    print(
        "TUNED RANDOM FOREST"
    )

    print("-" * 50)

    print(
        f"MAE                : "
        f"{tuned_metrics['mae']:.4f}"
    )

    print(
        f"RMSE               : "
        f"{tuned_metrics['rmse']:.4f}"
    )

    print(
        f"R2 Score           : "
        f"{tuned_metrics['r2_score']:.4f}"
    )

    print(
        f"Explained Variance : "
        f"{tuned_metrics['explained_variance']:.4f}"
    )

    # --------------------------------------------------------
    # Compare models
    # --------------------------------------------------------

    print("\n")
    print(
        "MODEL COMPARISON"
    )

    print("-" * 70)

    comparison = pd.DataFrame(
        [
            {
                "Model": "Baseline Random Forest",
                "MAE": baseline_metrics[
                    "mae"
                ],
                "RMSE": baseline_metrics[
                    "rmse"
                ],
                "R2": baseline_metrics[
                    "r2_score"
                ],
                "Explained Variance":
                    baseline_metrics[
                        "explained_variance"
                    ],
            },
            {
                "Model": "Tuned Random Forest",
                "MAE": tuned_metrics[
                    "mae"
                ],
                "RMSE": tuned_metrics[
                    "rmse"
                ],
                "R2": tuned_metrics[
                    "r2_score"
                ],
                "Explained Variance":
                    tuned_metrics[
                        "explained_variance"
                    ],
            },
        ]
    )

    print(
        comparison.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # Improvement
    # --------------------------------------------------------

    r2_improvement = (
        tuned_metrics["r2_score"]
        - baseline_metrics["r2_score"]
    )

    mae_improvement = (
        baseline_metrics["mae"]
        - tuned_metrics["mae"]
    )

    rmse_improvement = (
        baseline_metrics["rmse"]
        - tuned_metrics["rmse"]
    )

    print("\n")
    print(
        "IMPROVEMENT AFTER TUNING"
    )

    print("-" * 50)

    print(
        f"R2 improvement: "
        f"{r2_improvement:.4f}"
    )

    print(
        f"MAE improvement: "
        f"{mae_improvement:.4f}"
    )

    print(
        f"RMSE improvement: "
        f"{rmse_improvement:.4f}"
    )

    # --------------------------------------------------------
    # Save tuned model
    # --------------------------------------------------------

    tuned_model_path = (
        BASE_DIR /
        "traffic_model_tuned.pkl"
    )

    joblib.dump(
        tuned_model,
        tuned_model_path,
    )

    # --------------------------------------------------------
    # Save comparison
    # --------------------------------------------------------

    comparison_path = (
        OUTPUT_DIR /
        "model_comparison.csv"
    )

    comparison.to_csv(
        comparison_path,
        index=False,
    )

    # --------------------------------------------------------
    # Save tuning results
    # --------------------------------------------------------

    tuning_results = {

        "baseline_model": {
            "algorithm":
                "RandomForestRegressor",
            "parameters": {
                "n_estimators": 200,
                "random_state": 42,
            },
            **baseline_metrics,
        },

        "tuned_model": {
            "algorithm":
                "RandomForestRegressor",
            "best_parameters":
                grid_search.best_params_,
            "best_cross_validation_r2":
                float(
                    grid_search.best_score_
                ),
            **tuned_metrics,
        },

        "improvement": {
            "r2":
                float(r2_improvement),
            "mae":
                float(mae_improvement),
            "rmse":
                float(rmse_improvement),
        },
    }

    tuning_results_path = (
        OUTPUT_DIR /
        "tuning_results.json"
    )

    with open(
        tuning_results_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            tuning_results,
            file,
            indent=4,
        )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print("\n")
    print(
        "FILES GENERATED"
    )

    print("-" * 50)

    print(
        f"Tuned model      : "
        f"{tuned_model_path}"
    )

    print(
        f"Model comparison : "
        f"{comparison_path}"
    )

    print(
        f"Tuning results   : "
        f"{tuning_results_path}"
    )

    print("\n")
    print(
        "Hyperparameter tuning completed successfully."
    )

    print("=" * 70)


if __name__ == "__main__":
    tune_model()