"""Pydantic request and response schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field, validator

from domain import LOCATION_META, WEATHER_ALIASES


class TrafficInput(BaseModel):
    location: str
    traffic_volume: int = Field(..., ge=0, le=500)
    average_speed: float = Field(..., ge=0, le=120)
    weather: str

    @validator("location")
    def validate_location(cls, value: str) -> str:
        if value not in LOCATION_META:
            raise ValueError("Invalid location selected")
        return value

    @validator("weather")
    def validate_weather(cls, value: str) -> str:
        if value not in WEATHER_ALIASES:
            raise ValueError("Invalid weather condition")
        return value


class ForecastInput(BaseModel):
    location: str
    weather: str

    @validator("location")
    def validate_location(cls, value: str) -> str:
        if value not in LOCATION_META:
            raise ValueError("Invalid location")
        return value

    @validator("weather")
    def validate_weather(cls, value: str) -> str:
        if value not in WEATHER_ALIASES:
            raise ValueError("Invalid weather condition")
        return value


class CommuteInput(BaseModel):
    origin: str
    destination: str
    preferred_arrival: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @validator("origin", "destination")
    def validate_known_location(cls, value: str) -> str:
        if value not in LOCATION_META:
            raise ValueError("Invalid location")
        return value

    @validator("destination")
    def validate_different_destination(cls, value: str, values: dict) -> str:
        if values.get("origin") == value:
            raise ValueError("Origin and destination must be different")
        return value


class LocationResponse(BaseModel):
    name: str
    lat: float
    lon: float
    description: str


class LocationsResponse(BaseModel):
    locations: List[LocationResponse]


class TrafficIncident(BaseModel):
    location_name: str
    severity: str
    disruption_type: str
    description: Optional[str] = None
    source: str = "ASTraM"
