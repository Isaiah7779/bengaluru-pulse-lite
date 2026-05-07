import pandas as pd

# Load dataset
df = pd.read_csv(r"C:\Users\IZY\OneDrive\Desktop\BengaluruPulseLite\backend\Banglore_traffic_Dataset.csv")

# Show column names
print(df.columns)

# Filter Marathahalli Bridge data
marathahalli_data = df[
    df["Road/Intersection Name"] == "Marathahalli Bridge"
]

# Save filtered dataset
marathahalli_data.to_csv(
    "traffic_dataset.csv",
    index=False
)

print("Dataset filtered successfully!")
print(marathahalli_data.head())