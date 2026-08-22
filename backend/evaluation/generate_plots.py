"""
Bengaluru Pulse - Experimental Result Visualization

Generates publication/project-ready plots from the final
tuned Random Forest evaluation results.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

RESULTS_PATH = BASE_DIR / "final_actual_vs_predicted.csv"
FEATURE_PATH = BASE_DIR / "final_feature_importance.csv"
COMPARISON_PATH = BASE_DIR / "model_comparison.csv"

OUTPUT_DIR = BASE_DIR / "plots"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 1. ACTUAL VS PREDICTED
# ============================================================

def plot_actual_vs_predicted():

    data = pd.read_csv(
        RESULTS_PATH
    )

    actual = data["Actual Congestion"]
    predicted = data["Predicted Congestion"]

    plt.figure(
        figsize=(8, 6)
    )

    plt.scatter(
        actual,
        predicted,
        alpha=0.7,
    )

    minimum = min(
        actual.min(),
        predicted.min(),
    )

    maximum = max(
        actual.max(),
        predicted.max(),
    )

    plt.plot(
        [minimum, maximum],
        [minimum, maximum],
        linestyle="--",
    )

    plt.xlabel(
        "Actual Congestion Level"
    )

    plt.ylabel(
        "Predicted Congestion Level"
    )

    plt.title(
        "Actual vs Predicted Congestion"
    )

    plt.grid(
        alpha=0.3
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR /
        "actual_vs_predicted.png"
    )

    plt.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Created: {output}"
    )


# ============================================================
# 2. FEATURE IMPORTANCE
# ============================================================

def plot_feature_importance():

    data = pd.read_csv(
        FEATURE_PATH
    )

    data = data.sort_values(
        "Importance",
        ascending=True,
    )

    plt.figure(
        figsize=(8, 5)
    )

    plt.barh(
        data["Feature"],
        data["Importance"],
    )

    plt.xlabel(
        "Importance"
    )

    plt.ylabel(
        "Feature"
    )

    plt.title(
        "Random Forest Feature Importance"
    )

    plt.grid(
        axis="x",
        alpha=0.3,
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR /
        "feature_importance.png"
    )

    plt.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Created: {output}"
    )


# ============================================================
# 3. ERROR DISTRIBUTION
# ============================================================

def plot_error_distribution():

    data = pd.read_csv(
        RESULTS_PATH
    )

    errors = data["Error"]

    plt.figure(
        figsize=(8, 5)
    )

    plt.hist(
        errors,
        bins=20,
        edgecolor="black",
    )

    plt.axvline(
        0,
        linestyle="--",
    )

    plt.xlabel(
        "Prediction Error"
    )

    plt.ylabel(
        "Frequency"
    )

    plt.title(
        "Prediction Error Distribution"
    )

    plt.grid(
        axis="y",
        alpha=0.3,
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR /
        "error_distribution.png"
    )

    plt.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Created: {output}"
    )


# ============================================================
# 4. MODEL COMPARISON
# ============================================================

def plot_model_comparison():

    data = pd.read_csv(
        COMPARISON_PATH
    )

    models = data["Model"]

    # --------------------------------------------------------
    # R2
    # --------------------------------------------------------

    plt.figure(
        figsize=(8, 5)
    )

    plt.bar(
        models,
        data["R2"],
    )

    plt.ylabel(
        "R² Score"
    )

    plt.title(
        "Baseline vs Tuned Random Forest"
    )

    plt.ylim(
        0,
        1,
    )

    plt.xticks(
        rotation=10
    )

    plt.grid(
        axis="y",
        alpha=0.3,
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR /
        "model_r2_comparison.png"
    )

    plt.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Created: {output}"
    )

    # --------------------------------------------------------
    # MAE and RMSE
    # --------------------------------------------------------

    x = np.arange(
        len(models)
    )

    width = 0.35

    plt.figure(
        figsize=(8, 5)
    )

    plt.bar(
        x - width / 2,
        data["MAE"],
        width,
        label="MAE",
    )

    plt.bar(
        x + width / 2,
        data["RMSE"],
        width,
        label="RMSE",
    )

    plt.xticks(
        x,
        models,
        rotation=10,
    )

    plt.ylabel(
        "Error"
    )

    plt.title(
        "Baseline vs Tuned Model Error"
    )

    plt.legend()

    plt.grid(
        axis="y",
        alpha=0.3,
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR /
        "model_error_comparison.png"
    )

    plt.savefig(
        output,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close()

    print(
        f"Created: {output}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "BENGALURU PULSE - GENERATING EXPERIMENTAL PLOTS"
    )
    print("=" * 60)

    plot_actual_vs_predicted()

    plot_feature_importance()

    plot_error_distribution()

    plot_model_comparison()

    print("\n")
    print(
        "All experimental plots generated successfully."
    )

    print(
        f"\nOutput directory:\n{OUTPUT_DIR}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()