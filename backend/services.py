"""Legacy (V1) congestion estimator.

The V1 RandomForest estimates a same-day congestion index from *observed*
traffic volume and average speed. It is not a forecast. Its published metrics
(R² 0.96) came from a random train/test split on 492 daily rows and are not
valid forecasting evidence — see docs/ML_PIPELINE.md. The endpoint is kept for
backward compatibility only and is labelled as legacy in every response.

The former simulated services (random forecasts, hotspots, trends and
incidents) were removed: Bengaluru Pulse does not fabricate traffic data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

import joblib
import pandas as pd

from core.settings import Settings
from database import database
from domain import LOCATION_META, get_signal, get_traffic_status, normalize_weather
from schemas import TrafficInput

logger = logging.getLogger(__name__)

LEGACY_NOTICE = (
    "Legacy V1 estimator: maps observed volume/speed to a congestion index using a model "
    "evaluated only with a random split. Not a forecast; not used for routing."
)


class ModelBundle:
    """Loads and owns the legacy ML artifacts."""

    def __init__(self, settings: Settings) -> None:
        self.model = self._load_artifact(settings.model_path)
        self.area_encoder = self._load_artifact(settings.area_encoder_path)
        self.road_encoder = self._load_artifact(settings.road_encoder_path)
        self.weather_encoder = self._load_artifact(settings.weather_encoder_path)

    @staticmethod
    def _load_artifact(path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"Required model artifact not found: {path.name}")
        logger.info("Loading legacy ML artifact: %s", path.name)
        return joblib.load(path)

    def predict(self, data: TrafficInput) -> Dict[str, Any]:
        meta = LOCATION_META[data.location]
        model_weather = normalize_weather(data.weather)
        input_data = pd.DataFrame(
            [
                {
                    "Area Name": self.area_encoder.transform([meta["area"]])[0],
                    "Road/Intersection Name": self.road_encoder.transform([meta["road"]])[0],
                    "Traffic Volume": data.traffic_volume,
                    "Average Speed": data.average_speed,
                    "Weather Conditions": self.weather_encoder.transform([model_weather])[0],
                }
            ]
        )
        raw_prediction = float(self.model.predict(input_data)[0])
        predicted_value = round(raw_prediction, 2)
        traffic_status = get_traffic_status(predicted_value)
        try:
            database.save_prediction(
                location=data.location,
                traffic_volume=data.traffic_volume,
                average_speed=data.average_speed,
                weather=data.weather,
                predicted_congestion=predicted_value,
                traffic_status=traffic_status,
            )
        except Exception:
            logger.exception("Failed to save legacy prediction")
        return {
            "legacy": True,
            "notice": LEGACY_NOTICE,
            "predicted_congestion": predicted_value,
            "traffic_status": traffic_status,
            "signal": get_signal(predicted_value),
            "model_weather": model_weather,
            "location_meta": {"lat": meta["lat"], "lon": meta["lon"], "description": meta["description"]},
        }
