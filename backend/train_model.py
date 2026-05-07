import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score
import joblib

# LOAD FULL DATASET
df = pd.read_csv("Banglore_traffic_Dataset.csv")

# REMOVE MISSING VALUES
df = df.dropna()

# ENCODERS

area_encoder = LabelEncoder()
road_encoder = LabelEncoder()
weather_encoder = LabelEncoder()

# ENCODE CATEGORICAL DATA

df['Area Name'] = area_encoder.fit_transform(
    df['Area Name']
)

df['Road/Intersection Name'] = road_encoder.fit_transform(
    df['Road/Intersection Name']
)

df['Weather Conditions'] = weather_encoder.fit_transform(
    df['Weather Conditions']
)

# FEATURES

X = df[[
    'Area Name',
    'Road/Intersection Name',
    'Traffic Volume',
    'Average Speed',
    'Weather Conditions'
]]

# TARGET

y = df['Congestion Level']

# SPLIT DATA

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

# MODEL

model = RandomForestRegressor()

model.fit(X_train, y_train)

# PREDICTIONS

predictions = model.predict(X_test)

# METRICS

mae = mean_absolute_error(y_test, predictions)
r2 = r2_score(y_test, predictions)

print(f"Mean Absolute Error: {mae}")
print(f"R2 Score: {r2}")

# SAVE EVERYTHING

joblib.dump(model, "traffic_model.pkl")
joblib.dump(area_encoder, "area_encoder.pkl")
joblib.dump(road_encoder, "road_encoder.pkl")
joblib.dump(weather_encoder, "weather_encoder.pkl")

print("Multi-location AI model trained successfully!")