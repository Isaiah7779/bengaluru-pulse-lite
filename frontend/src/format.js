export function minutes(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "–";
  const m = seconds / 60;
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60);
  return `${h} h ${Math.round(m - h * 60)} min`;
}

export function km(meters) {
  if (meters == null) return "–";
  return meters < 1000 ? `${Math.round(meters)} m` : `${(meters / 1000).toFixed(1)} km`;
}

export function clock(iso) {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("en-IN", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" });
}

export function ago(iso) {
  if (!iso) return "never";
  const mins = (Date.now() - new Date(iso).getTime()) / 60000;
  if (mins < 1) return "just now";
  if (mins < 60) return `${Math.round(mins)} min ago`;
  if (mins < 1440) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} d ago`;
}

export const BASIS_LABEL = {
  traffic_live: "Live traffic (TomTom)",
  traffic_predicted: "Predicted traffic (TomTom)",
  free_flow: "Free-flow estimate (OSRM)",
};

export const CLASS_LABEL = {
  reference: "Reference",
  shortcut: "Shortcut",
  longcut: "Longcut",
  alternative: "Alternative",
  unclassified: "Unclassified",
};

export function signedDelta(value, unit) {
  if (value == null) return "";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  return `${sign}${Math.abs(value).toFixed(unit === "km" ? 2 : 1)} ${unit}`;
}
