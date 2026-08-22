"""
Bengaluru Pulse - Data Preprocessing Pipeline

This script:
1. Loads the original dataset
2. Removes duplicates
3. Handles missing values
4. Validates required columns
5. Cleans text columns
6. Saves the processed dataset
"""

from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent

SOURCE_DATASET = BASE_DIR / "Banglore_traffic_Dataset.csv"
OUTPUT_DATASET = BASE_DIR / "processed_dataset.csv"

REQUIRED_COLUMNS = [
    "Area Name",
    "Road/Intersection Name",
    "Traffic Volume",
    "Average Speed",
    "Weather Conditions",
    "Congestion Level",
]


def preprocess_dataset():

    if not SOURCE_DATASET.exists():
        raise FileNotFoundError(f"Dataset not found: {SOURCE_DATASET}")

    print("=" * 60)
    print("BENGALURU PULSE DATA PREPROCESSING")
    print("=" * 60)

    df = pd.read_csv(SOURCE_DATASET)

    print(f"\nOriginal Shape : {df.shape}")

    # Keep only required columns
    df = df[REQUIRED_COLUMNS]

    # Remove duplicate rows
    duplicates = df.duplicated().sum()
    df = df.drop_duplicates()

    # Remove rows with missing values
    missing = df.isnull().sum().sum()
    df = df.dropna()

    # Clean text columns
    text_columns = [
        "Area Name",
        "Road/Intersection Name",
        "Weather Conditions",
    ]

    for col in text_columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
            .str.title()
        )

    # Reset index
    df.reset_index(drop=True, inplace=True)

    # Save processed dataset
    df.to_csv(OUTPUT_DATASET, index=False)

    print(f"\nDuplicates Removed : {duplicates}")
    print(f"Missing Values Removed : {missing}")

    print(f"\nProcessed Shape : {df.shape}")

    print(f"\nProcessed dataset saved to:")
    print(OUTPUT_DATASET)

    print("\nSample Data\n")
    print(df.head())

    print("\nPreprocessing Completed Successfully.")

    return df


if __name__ == "__main__":
    preprocess_dataset()