"""
Bengaluru Pulse - Final Tuned Model Evaluation

Evaluates the final tuned Random Forest model using the same
train/test split used during model development.

Generates:
1. Final performance metrics
2. Actual vs predicted values
3. Prediction errors
4. Feature importance
5. Error statistics
6. JSON summary
7. CSV files for report/visualization
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
from sklearn.preprocessing import LabelEncoder


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATASET_PATH = BASE_DIR / "traffic_dataset.csv"

MODEL_PATH = BASE_DIR / "traffic_model_tuned.pkl"

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
            f"Dataset not found:\n{DATASET_PATH}"
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
            f"Dataset is missing columns: "
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
# MAIN EVALUATION
# ============================================================

def evaluate_final_model():

    print("=" * 70)
    print(
        "BENGALURU PULSE - FINAL MODEL EVALUATION"
    )
    print("=" * 70)

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
        f"Training samples: {len(X_train)}"
    )

    print(
        f"Testing samples: {len(X_test)}"
    )

    # --------------------------------------------------------
    # Load final tuned model
    # --------------------------------------------------------

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Tuned model not found:\n{MODEL_PATH}"
        )

    model = joblib.load(
        MODEL_PATH
    )

    print(
        f"\nLoaded model:"
    )

    print(
        "RandomForestRegressor "
        "(Tuned)"
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

    explained_variance = (
        explained_variance_score(
            y_test,
            predictions,
        )
    )

    # --------------------------------------------------------
    # Error statistics
    # --------------------------------------------------------

    errors = (
        y_test.values - predictions
    )

    absolute_errors = np.abs(
        errors
    )

    mean_error = np.mean(
        errors
    )

    median_absolute_error = np.median(
        absolute_errors
    )

    max_absolute_error = np.max(
        absolute_errors
    )

    min_absolute_error = np.min(
        absolute_errors
    )

    # --------------------------------------------------------
    # Print final results
    # --------------------------------------------------------

    print("\n")
    print(
        "FINAL MODEL PERFORMANCE"
    )

    print("-" * 50)

    print(
        f"MAE                : "
        f"{mae:.4f}"
    )

    print(
        f"RMSE               : "
        f"{rmse:.4f}"
    )

    print(
        f"R2 Score           : "
        f"{r2:.4f}"
    )

    print(
        f"Explained Variance : "
        f"{explained_variance:.4f}"
    )

    print("\n")
    print(
        "ERROR ANALYSIS"
    )

    print("-" * 50)

    print(
        f"Mean Error             : "
        f"{mean_error:.4f}"
    )

    print(
        f"Median Absolute Error  : "
        f"{median_absolute_error:.4f}"
    )

    print(
        f"Minimum Absolute Error : "
        f"{min_absolute_error:.4f}"
    )

    print(
        f"Maximum Absolute Error : "
        f"{max_absolute_error:.4f}"
    )

    # ========================================================
    # ACTUAL VS PREDICTED
    # ========================================================

    results = pd.DataFrame(
        {
            "Actual Congestion":
                y_test.values,

            "Predicted Congestion":
                predictions,

            "Error":
                errors,

            "Absolute Error":
                absolute_errors,
        }
    )

    results_path = (
        OUTPUT_DIR /
        "final_actual_vs_predicted.csv"
    )

    results.to_csv(
        results_path,
        index=False,
    )

    # ========================================================
    # FEATURE IMPORTANCE
    # ========================================================

    feature_importance_path = (
        OUTPUT_DIR /
        "final_feature_importance.csv"
    )

    if hasattr(
        model,
        "feature_importances_",
    ):

        feature_importance = (
            pd.DataFrame(
                {
                    "Feature":
                        FEATURE_COLUMNS,

                    "Importance":
                        model.feature_importances_,
                }
            )
            .sort_values(
                "Importance",
                ascending=False,
            )
        )

        feature_importance.to_csv(
            feature_importance_path,
            index=False,
        )

        print("\n")
        print(
            "FINAL FEATURE IMPORTANCE"
        )

        print("-" * 50)

        for _, row in (
            feature_importance.iterrows()
        ):

            print(
                f"{row['Feature']}: "
                f"{row['Importance']:.4f}"
            )

    # ========================================================
    # METRICS JSON
    # ========================================================

    metrics = {

        "model":
            "Tuned Random Forest Regressor",

        "dataset":
            "Bengaluru Traffic Dataset",

        "dataset_records":
            int(len(dataframe)),

        "training_samples":
            int(len(X_train)),

        "testing_samples":
            int(len(X_test)),

        "test_size":
            0.20,

        "random_state":
            42,

        "mae":
            round(float(mae), 6),

        "rmse":
            round(float(rmse), 6),

        "r2_score":
            round(float(r2), 6),

        "explained_variance":
            round(
                float(
                    explained_variance
                ),
                6,
            ),

        "mean_error":
            round(
                float(mean_error),
                6,
            ),

        "median_absolute_error":
            round(
                float(
                    median_absolute_error
                ),
                6,
            ),

        "minimum_absolute_error":
            round(
                float(
                    min_absolute_error
                ),
                6,
            ),

        "maximum_absolute_error":
            round(
                float(
                    max_absolute_error
                ),
                6,
            ),
    }

    metrics_path = (
        OUTPUT_DIR /
        "final_evaluation_metrics.json"
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

    # ========================================================
    # TEXT REPORT
    # ========================================================

    report_path = (
        OUTPUT_DIR /
        "final_evaluation_report.txt"
    )

    with open(
        report_path,
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            "BENGALURU PULSE\n"
        )

        file.write(
            "FINAL MODEL EVALUATION REPORT\n"
        )

        file.write(
            "=" * 60
            + "\n\n"
        )

        file.write(
            "Model: Tuned Random Forest Regressor\n"
        )

        file.write(
            f"Dataset records: {len(dataframe)}\n"
        )

        file.write(
            f"Training samples: {len(X_train)}\n"
        )

        file.write(
            f"Testing samples: {len(X_test)}\n\n"
        )

        file.write(
            "PERFORMANCE METRICS\n"
        )

        file.write(
            "-" * 40
            + "\n"
        )

        file.write(
            f"MAE: {mae:.6f}\n"
        )

        file.write(
            f"RMSE: {rmse:.6f}\n"
        )

        file.write(
            f"R2 Score: {r2:.6f}\n"
        )

        file.write(
            f"Explained Variance: "
            f"{explained_variance:.6f}\n\n"
        )

        file.write(
            "ERROR ANALYSIS\n"
        )

        file.write(
            "-" * 40
            + "\n"
        )

        file.write(
            f"Mean Error: "
            f"{mean_error:.6f}\n"
        )

        file.write(
            f"Median Absolute Error: "
            f"{median_absolute_error:.6f}\n"
        )

        file.write(
            f"Minimum Absolute Error: "
            f"{min_absolute_error:.6f}\n"
        )

        file.write(
            f"Maximum Absolute Error: "
            f"{max_absolute_error:.6f}\n"
        )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    print("\n")
    print(
        "FILES GENERATED"
    )

    print("-" * 50)

    print(
        f"Metrics:"
        f"\n{metrics_path}"
    )

    print(
        f"\nActual vs Predicted:"
        f"\n{results_path}"
    )

    if hasattr(
        model,
        "feature_importances_",
    ):

        print(
            f"\nFeature Importance:"
            f"\n{feature_importance_path}"
        )

    print(
        f"\nReport:"
        f"\n{report_path}"
    )

    print("\n")
    print(
        "FINAL MODEL EVALUATION "
        "COMPLETED SUCCESSFULLY."
    )

    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    evaluate_final_model()