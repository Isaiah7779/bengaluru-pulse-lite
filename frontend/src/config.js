// Runtime configuration (CRA bakes REACT_APP_* in at build time).
// Default: same-origin "/api" in production builds (nginx proxies it to FastAPI, so the
// web app works unchanged behind localhost, a LAN IP, a tunnel or a real domain);
// the CRA dev server (npm start) talks to the backend directly on localhost:8000.
const DEFAULT_API_BASE_URL = process.env.NODE_ENV === "production" ? "/api" : "http://localhost:8000";
export const API_BASE_URL = (process.env.REACT_APP_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/$/, "");

// OpenStreetMap standard tiles: free for light use with attribution
// (https://operations.osmfoundation.org/policies/tiles/). Override for heavier use.
export const TILE_URL = process.env.REACT_APP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const TILE_ATTRIBUTION =
  process.env.REACT_APP_TILE_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export const BENGALURU_CENTER = [12.9716, 77.5946];
export const BENGALURU_BOUNDS = [
  [12.7, 77.3],
  [13.3, 77.95],
];

export const ROUTE_COLORS = ["#2563eb", "#9333ea", "#0d9488", "#ea580c", "#db2777", "#4b5563"];

export const CONGESTION_COLORS = {
  FREE: "#16a34a",
  MODERATE: "#ca8a04",
  HEAVY: "#ea580c",
  SEVERE: "#dc2626",
  CLOSED: "#7f1d1d",
};
