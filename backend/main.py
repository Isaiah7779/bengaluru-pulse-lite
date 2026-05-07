from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from pydantic import BaseModel
import pandas as pd
import joblib

# Create app
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load trained model
model = joblib.load("traffic_model.pkl")

# Load weather encoder
weather_encoder = joblib.load("weather_encoder.pkl")

# Input structure
class TrafficInput(BaseModel):
    traffic_volume: int
    average_speed: float
    weather: str

# Home route
@app.get("/")
def home():
    return {
        "message": "Bengaluru Pulse Lite API Running"
    }

# Prediction route
@app.post("/predict")
def predict(data: TrafficInput):

    # Encode weather
    weather_value = weather_encoder.transform(
        [data.weather]
    )[0]

    # Create dataframe
    input_data = pd.DataFrame([{
        'Traffic Volume': data.traffic_volume,
        'Average Speed': data.average_speed,
        'Weather Conditions': weather_value
    }])

    # Predict congestion
    prediction = model.predict(input_data)

    return {
        "predicted_congestion": round(float(prediction[0]), 2)
    }