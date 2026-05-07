import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

# Load dataset
df = pd.read_csv("traffic_dataset.csv")

# Show columns
print(df.columns)

# Remove missing values
df = df.dropna()

# Encode weather conditions
weather_encoder = LabelEncoder()
df['Weather Conditions'] = weather_encoder.fit_transform(df['Weather Conditions'])

# Features (inputs)
X = df[[
    'Traffic Volume',
    'Average Speed',
    'Weather Conditions'
]]

# Target (output)
y = df['Congestion Level']

# Split dataset
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# Train regression model
model = RandomForestRegressor()

model.fit(X_train, y_train)

# Predictions
predictions = model.predict(X_test)

# Evaluation
mae = mean_absolute_error(y_test, predictions)
r2 = r2_score(y_test, predictions)

print(f"Mean Absolute Error: {mae}")
print(f"R2 Score: {r2}")

# Save model
joblib.dump(model, "traffic_model.pkl")
joblib.dump(weather_encoder, "weather_encoder.pkl")

print("Regression model trained successfully!")