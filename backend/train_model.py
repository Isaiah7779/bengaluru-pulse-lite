
"""Train and persist the Bengaluru Pulse congestion model (Version 1)."""

from pathlib import Path
import os
import joblib
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "Banglore_traffic_Dataset.csv"

FEATURE_COLUMNS = [
    "Area Name",
    "Road/Intersection Name",
    "Traffic Volume",
    "Average Speed",
    "Weather Conditions",
]

TARGET_COLUMN = "Congestion Level"

MODEL_DIR = BASE_DIR
EVAL_DIR = BASE_DIR / "evaluation"
EVAL_DIR.mkdir(exist_ok=True)


def load_dataset():
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    df = pd.read_csv(DATASET_PATH)

    required = FEATURE_COLUMNS + [TARGET_COLUMN]
    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.drop_duplicates()
    df = df.dropna(subset=required)

    return df


def encode_dataframe(df):
    df = df.copy()

    area_encoder = LabelEncoder()
    road_encoder = LabelEncoder()
    weather_encoder = LabelEncoder()

    df["Area Name"] = area_encoder.fit_transform(df["Area Name"])
    df["Road/Intersection Name"] = road_encoder.fit_transform(df["Road/Intersection Name"])
    df["Weather Conditions"] = weather_encoder.fit_transform(df["Weather Conditions"])

    return df, area_encoder, road_encoder, weather_encoder


def evaluate_model(name, model, x_train, x_test, y_train, y_test):
    model.fit(x_train, y_train)

    preds = model.predict(x_test)

    mae = mean_absolute_error(y_test, preds)
    mse = mean_squared_error(y_test, preds)
    rmse = mse ** 0.5
    r2 = r2_score(y_test, preds)

    return {
        "Model": name,
        "MAE": round(mae, 4),
        "MSE": round(mse, 4),
        "RMSE": round(rmse, 4),
        "R2": round(r2, 4),
        "Estimator": model,
    }


def main():

    print("=" * 60)
    print("BENGALURU PULSE MODEL TRAINING")
    print("=" * 60)

    df = load_dataset()

    encoded_df, area_encoder, road_encoder, weather_encoder = encode_dataframe(df)

    X = encoded_df[FEATURE_COLUMNS]
    y = encoded_df[TARGET_COLUMN]

    x_train, x_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
    )

    models = {
        "Linear Regression": LinearRegression(),
        "Decision Tree": DecisionTreeRegressor(random_state=42),
        "Random Forest": RandomForestRegressor(
            n_estimators=200,
            random_state=42,
            n_jobs=-1,
        ),
        "Gradient Boosting": GradientBoostingRegressor(random_state=42),
    }

    results = []

    for name, model in models.items():
        print(f"\nTraining {name}...")
        metrics = evaluate_model(
            name,
            model,
            x_train,
            x_test,
            y_train,
            y_test,
        )
        results.append(metrics)

    comparison = pd.DataFrame(
        [
            {
                "Model": r["Model"],
                "MAE": r["MAE"],
                "MSE": r["MSE"],
                "RMSE": r["RMSE"],
                "R2": r["R2"],
            }
            for r in results
        ]
    )

    comparison = comparison.sort_values("R2", ascending=False)

    comparison.to_csv(
        EVAL_DIR / "model_comparison.csv",
        index=False,
    )

    best_name = comparison.iloc[0]["Model"]

    best_model = None
    for r in results:
        if r["Model"] == best_name:
            best_model = r["Estimator"]
            break

    print("\n")
    print("=" * 60)
    print("MODEL COMPARISON")
    print(comparison)
    print("=" * 60)

    print(f"\nBest Model : {best_name}")

    joblib.dump(best_model, MODEL_DIR / "traffic_model.pkl")
    joblib.dump(area_encoder, MODEL_DIR / "area_encoder.pkl")
    joblib.dump(road_encoder, MODEL_DIR / "road_encoder.pkl")
    joblib.dump(weather_encoder, MODEL_DIR / "weather_encoder.pkl")

    print("\nModel saved successfully.")
    print("Comparison saved to evaluation/model_comparison.csv")


if __name__ == "__main__":
    main()
