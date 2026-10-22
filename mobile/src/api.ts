import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";

// Backend base URL (the same API the web app uses, i.e. ".../api"), in priority order:
// 1. A server address saved on this device (Account → Server). Lets an installed
//    build follow a changing address (e.g. a temporary HTTPS tunnel) without a rebuild.
// 2. EXPO_PUBLIC_API_BASE_URL, inlined per build profile (eas.json) — use a stable
//    HTTPS URL for distributed builds. Not a secret.
// 3. Development only: the laptop's LAN address that the Expo dev server runs on
//    (Constants.expoConfig.hostUri, e.g. "192.168.1.7:8081"), reaching the API
//    through nginx on port 8080 under /api (port 8000 is not exposed on the network).
// Nothing else is guessed: no localhost (on a phone that is the phone itself) and
// no emulator alias. Without a server, requests fail with an explanatory message.
const SERVER_KEY = "pulse_server_url";
let override: string | null = null;

export function normaliseServerUrl(input: string): string {
  let url = input.trim().replace(/\/+$/, "");
  if (url && !/^https?:\/\//i.test(url)) url = `https://${url}`;
  if (url && !/\/api$/i.test(url)) url = `${url}/api`;
  return url;
}

function resolveApiBaseUrl(): { url: string; source: string } {
  if (override) return { url: override, source: "set on this device" };
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (configured) return { url: configured.replace(/\/$/, ""), source: "build configuration" };
  const host = Constants.expoConfig?.hostUri?.split(":")[0];
  if (host && host !== "localhost" && host !== "127.0.0.1") {
    return { url: `http://${host}:8080/api`, source: "Expo dev server (LAN)" };
  }
  return { url: "", source: "not configured" };
}

export function apiBaseUrl(): string {
  return resolveApiBaseUrl().url;
}

export function apiBaseSource(): string {
  return resolveApiBaseUrl().source;
}

export async function loadServerOverride(): Promise<void> {
  override = await SecureStore.getItemAsync(SERVER_KEY);
}

/** Check that `candidate` is a Bengaluru Pulse API, then save it on this device. */
export async function setServerOverride(candidate: string | null): Promise<string | null> {
  if (!candidate) {
    override = null;
    await SecureStore.deleteItemAsync(SERVER_KEY);
    return null;
  }
  const url = normaliseServerUrl(candidate);
  let ok = false;
  try {
    const res = await fetch(`${url}/health`, { headers: { Accept: "application/json" } });
    ok = res.ok && (await res.json().catch(() => null))?.status === "ok";
  } catch {
    ok = false;
  }
  if (!ok) throw new ApiError(0, "server_unreachable", `No Bengaluru Pulse server answered at ${url}.`);
  override = url;
  await SecureStore.setItemAsync(SERVER_KEY, url);
  return url;
}

const TOKEN_KEY = "pulse_token";
let token: string | null = null;

export async function loadToken(): Promise<string | null> {
  token = await SecureStore.getItemAsync(TOKEN_KEY);
  return token;
}

export async function saveToken(value: string | null): Promise<void> {
  token = value;
  if (value) await SecureStore.setItemAsync(TOKEN_KEY, value);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

type Options = { method?: string; body?: unknown; params?: Record<string, string | number | undefined> };

export async function api<T = any>(path: string, { method = "GET", body, params }: Options = {}): Promise<T> {
  const base = apiBaseUrl();
  if (!base) {
    throw new ApiError(0, "server_not_configured", "No server is set. Open Account → Server and enter the Bengaluru Pulse address.");
  }
  let url = base + path;
  if (params) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join("&");
    if (qs) url += `?${qs}`;
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, "network_error", `Cannot reach the server at ${base}. Check the address in Account → Server.`);
  }
  if (res.status === 204) return null as T;
  const data: any = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    const fields = err?.code === "validation_error" && Array.isArray(err.fields)
      ? err.fields.map((f: any) => `${f.loc.filter((x: string) => x !== "body").join(".")}: ${f.msg}`).join("; ")
      : null;
    if (res.status === 401 && token) await saveToken(null);
    throw new ApiError(res.status, err?.code || `http_${res.status}`, fields || err?.message || `Request failed (HTTP ${res.status})`);
  }
  return data as T;
}

export type Place = { lat: number; lon: number; label: string };

export type RouteOption = {
  id: string;
  rank: number;
  is_reference: boolean;
  recommended: boolean;
  distance_m: number;
  free_flow_duration_s: number;
  eta_s: number;
  eta_basis: "traffic_live" | "traffic_predicted" | "free_flow";
  comparable: boolean;
  traffic: { traffic_delay_s: number; historic_s?: number | null; arrive_at?: string | null } | null;
  traffic_note?: string | null;
  classification: { type: string; reason: string; distance_diff_m?: number; time_diff_s?: number };
  incidents: { id: number; category: string; road?: string | null; source: string; lat: number; lon: number }[];
  explanation: string[];
  summary: string;
  geometry: { type: "LineString"; coordinates: [number, number][] };
  steps: { instruction?: string | null; distance_m: number }[];
};

export type RouteResponse = {
  recommendation: string;
  preference_note?: string | null;
  comparison_basis: string;
  departure_mode: "now" | "future";
  depart_at: string;
  warnings: string[];
  routes: RouteOption[];
  recommended_route_id: string;
  data_sources: { name: string; status: string; detail: string }[];
  vehicle_profile: { profile_status: string; notes: string };
  weather?: { description: string; temperature_c?: number | null; kind: string; attribution: string } | null;
};

export const BASIS_LABEL: Record<string, string> = {
  traffic_live: "Live traffic (TomTom)",
  traffic_predicted: "Predicted traffic (TomTom)",
  free_flow: "Free-flow estimate (OSRM)",
};

export function fmtMin(s?: number | null): string {
  if (s == null) return "–";
  const m = s / 60;
  return m < 60 ? `${Math.round(m)} min` : `${Math.floor(m / 60)} h ${Math.round(m % 60)} min`;
}

export function fmtKm(m?: number | null): string {
  if (m == null) return "–";
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`;
}
