from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import joblib

# CREATE FASTAPI APP

app = FastAPI()

# ENABLE CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# LOAD TRAINED MODEL

model = joblib.load("traffic_model.pkl")

# LOAD ENCODERS

area_encoder = joblib.load("area_encoder.pkl")
road_encoder = joblib.load("road_encoder.pkl")
weather_encoder = joblib.load("weather_encoder.pkl")

# LOCATION MAPPING
# IMPORTANT:
# Use ONLY roads that exist in dataset

location_mapping = {

    "Marathahalli Bridge": {
        "area": "Whitefield",
        "road": "Whitefield"
    },

    "Silk Board": {
        "area": "Koramangala",
        "road": "Koramangala"
    },

    "KR Puram": {
        "area": "Whitefield",
        "road": "Whitefield"
    },

    "Hebbal": {
        "area": "Hebbal",
        "road": "Hebbal"
    },

    "Whitefield": {
        "area": "Whitefield",
        "road": "Whitefield"
    },

    "Electronic City": {
        "area": "Electronic City",
        "road": "Electronic City"
    }
}

# INPUT MODEL

class TrafficInput(BaseModel):

    location: str
    traffic_volume: int
    average_speed: float
    weather: str

# HOME ROUTE

@app.get("/")
def home():

    return {
        "message": "Bengaluru Pulse Lite API Running"
    }

# PREDICT ROUTE

@app.post("/predict")
def predict(data: TrafficInput):

    try:

        # GET LOCATION DATA

        location_data = location_mapping[data.location]

        # ENCODE AREA

        area_value = area_encoder.transform(
            [location_data["area"]]
        )[0]

        # ENCODE ROAD

        road_value = road_encoder.transform(
            [location_data["road"]]
        )[0]

        # ENCODE WEATHER

        weather_value = weather_encoder.transform(
            [data.weather]
        )[0]

        # CREATE INPUT DATAFRAME

        input_data = pd.DataFrame([{

            'Area Name': area_value,

            'Road/Intersection Name': road_value,

            'Traffic Volume': data.traffic_volume,

            'Average Speed': data.average_speed,

            'Weather Conditions': weather_value
        }])

        # MODEL PREDICTION

        prediction = model.predict(input_data)

        predicted_value = round(
            float(prediction[0]),
            2
        )

        # SMART VALIDATION LOGIC

        if (
            data.traffic_volume < 20 and
            data.average_speed > 60
        ):
            predicted_value = 5.0

        elif (
            data.traffic_volume > 250 and
            data.average_speed < 20
        ):
            predicted_value += 5

        # LIMIT PREDICTION RANGE

        predicted_value = max(
            0,
            min(predicted_value, 30)
        )

        # RETURN RESPONSE

        return {

            "predicted_congestion":
                predicted_value,

            "traffic_status":
                get_traffic_status(
                    predicted_value
                )
        }

    except Exception as e:

        return {
            "error": str(e)
        }

# TRAFFIC STATUS FUNCTION

def get_traffic_status(value):

    if value < 8:
        return "LOW"

    elif value < 15:
        return "MODERATE"

    elif value < 22:
        return "HIGH"

    else:
        return "SEVERE"