const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL =
  process.env.REACT_APP_API_BASE_URL || DEFAULT_API_BASE_URL;

export const LOCATIONS = [
  "Marathahalli Bridge",
  "Silk Board",
  "KR Puram",
  "Hebbal",
  "Whitefield",
  "Electronic City",
];

export const WEATHER_OPTIONS = ["Sunny", "Cloudy", "Rainy"];

export const STATUS_COLORS = {
  LOW: "#00ff99",
  MODERATE: "#ffcc00",
  HIGH: "#ff8800",
  SEVERE: "#ff3333",
};
