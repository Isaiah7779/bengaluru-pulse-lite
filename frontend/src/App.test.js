import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";
import { api, ApiError, setToken } from "./api/client";
import PlaceSearch from "./components/PlaceSearch";
import RouteResults from "./components/RouteResults";
import { parseGpx } from "./pages/AccountPage";

// Leaflet needs a real layout engine; the map is covered by manual/browser testing.
jest.mock("./components/MapView", () => () => <div data-testid="map" />);

function respond(map) {
  global.fetch = jest.fn(async (url, opts = {}) => {
    const path = new URL(url).pathname;
    const handler = map[`${opts.method || "GET"} ${path}`] || map[path];
    if (!handler) return { ok: false, status: 404, json: async () => ({ error: { code: "not_found", message: `no mock for ${path}` } }) };
    const [status, body] = typeof handler === "function" ? handler(url, opts) : handler;
    return { ok: status < 400, status, json: async () => body };
  });
}

const VEHICLES = [200, { vehicles: [
  { vehicle: "car", available: true, profile_status: "dedicated", avoid_options: ["toll", "motorway", "ferry"] },
  { vehicle: "motorcycle", available: true, profile_status: "car_graph_approximation", avoid_options: ["toll"], notes: "Routed on the car graph." },
  { vehicle: "bicycle", available: true, profile_status: "dedicated", avoid_options: [] },
  { vehicle: "walk", available: false, profile_status: "dedicated", avoid_options: [] },
] }];

beforeEach(() => {
  setToken(null);
  window.location.hash = "";
});

const ME_USER = [200, { id: 2, email: "u@x.in", display_name: "Ravi", role: "user", created_at: "2026-10-01T00:00:00Z" }];

test("anonymous visitors only see the sign-in screen", async () => {
  respond({ "/v1/vehicles": VEHICLES });
  window.location.hash = "#/traffic";
  render(<App />);
  expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Find routes" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Traffic" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  // No Firebase config in this build: Google sign-in is not offered.
  expect(screen.queryByRole("button", { name: /Google/ })).not.toBeInTheDocument();
  expect(global.fetch).not.toHaveBeenCalled();
});

test("signing in opens the page the visitor asked for", async () => {
  respond({
    "/v1/vehicles": VEHICLES,
    "POST /v1/auth/login": [200, { access_token: "tok", user: ME_USER[1] }],
  });
  window.location.hash = "#/account";
  render(<App />);
  fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "u@x.in" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "Correct-Horse-9" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("heading", { name: "My account" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
});

test("admin link appears only for an admin user returned by the backend", async () => {
  setToken("t");
  respond({ "/v1/vehicles": VEHICLES, "/v1/auth/me": [200, { id: 1, email: "a@x.in", display_name: "Asha", role: "admin" }] });
  render(<App />);
  expect(await screen.findByRole("link", { name: "Admin" })).toBeInTheDocument();
});

test("route form requires both places", async () => {
  window.location.hash = "#/navigate";
  setToken("t");
  respond({ "/v1/vehicles": VEHICLES, "/v1/auth/me": ME_USER });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Find routes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose both a start and a destination");
  // An unavailable mode is disabled rather than silently served by another graph.
  await waitFor(() => expect(screen.getByLabelText("Walk")).toBeDisabled());
});

test("an expired session returns to the sign-in screen", async () => {
  setToken("old");
  respond({ "/v1/auth/me": [401, { error: { code: "token_expired", message: "Session expired; please sign in again" } }] });
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
});

test("api client surfaces the server's safe error message", async () => {
  respond({ "/v1/routes": [503, { error: { code: "routing_engine_unavailable", message: "Routing engine unreachable" } }] });
  await expect(api("/v1/routes")).rejects.toMatchObject({ status: 503, code: "routing_engine_unavailable", message: "Routing engine unreachable" });
  global.fetch = jest.fn(() => Promise.reject(new TypeError("Failed to fetch")));
  await expect(api("/health")).rejects.toBeInstanceOf(ApiError);
});

test("place search shows suggestions and returns the chosen place", async () => {
  jest.useFakeTimers();
  respond({
    "/v1/geocode/search": [200, { results: [{ id: "osm:n1", name: "Indiranagar", label: "Indiranagar, Bengaluru", category_label: "Area", lat: 12.97, lon: 77.64 }] }],
  });
  const onChange = jest.fn();
  render(<PlaceSearch label="From" value={null} onChange={onChange} onPickOnMap={() => {}} />);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "indira" } });
  await act(async () => {
    jest.advanceTimersByTime(300);
  });
  jest.useRealTimers();
  const option = await screen.findByRole("option", { name: /Indiranagar/ });
  fireEvent.mouseDown(option);
  expect(onChange).toHaveBeenCalledWith({ lat: 12.97, lon: 77.64, label: "Indiranagar" });
});

// TEST FIXTURE (shape of a /v1/routes response), not real traffic data.
const FIXTURE = {
  recommendation: "Recommended: fastest of 2 comparable route(s) on TomTom live traffic, 4.0 min ahead of the next.",
  preference_note: null,
  comparison_basis: "traffic_live",
  departure_mode: "now",
  depart_at: "2026-10-22T04:00:00Z",
  candidates_considered: 9,
  warnings: [],
  vehicle_profile: { profile_status: "dedicated" },
  reference_description: "OSRM's default route …",
  weather: null,
  data_sources: [
    { name: "osrm", status: "ok", detail: "car.lua graph" },
    { name: "pulse_forecast", status: "unavailable", detail: "no forecasting model has passed evaluation" },
  ],
  routes: [
    {
      id: "r1", rank: 1, is_reference: false, recommended: true, origin_kind: "corridor", distance_m: 12000, free_flow_duration_s: 900,
      eta_s: 1500, eta_basis: "traffic_live", comparable: true,
      traffic: { source: "tomtom", basis: "traffic_live", eta_s: 1500, traffic_delay_s: 300, no_traffic_s: 1200, provider_length_m: 12010, length_match_pct: 99.9 },
      classification: { type: "longcut", distance_diff_m: 2000, time_diff_s: -240, reason: "2.00 km longer but 4.0 min faster" },
      incidents: [], monitored_segments: [], explanation: ["Recommended: fastest of 2 comparable route(s)", "ETA 25 min"],
      summary: "Outer Ring Road", geometry: { type: "LineString", coordinates: [] }, steps: [{ instruction: "Head north", distance_m: 100 }],
    },
    {
      id: "r2", rank: 2, is_reference: true, recommended: false, origin_kind: "osrm_primary", distance_m: 10000, free_flow_duration_s: 840,
      eta_s: 1740, eta_basis: "traffic_live", comparable: true, traffic: null,
      classification: { type: "reference", reason: "Reference route" }, incidents: [{ id: 5, category: "jam", source: "tomtom", lat: 1, lon: 1 }],
      monitored_segments: [], explanation: ["ETA 29 min"], summary: "Hosur Road", geometry: { type: "LineString", coordinates: [] }, steps: [],
    },
  ],
};

test("route results show basis, classification, evidence and sources", () => {
  const onSelect = jest.fn();
  render(<RouteResults result={FIXTURE} selectedId="r1" onSelect={onSelect} />);
  expect(screen.getByRole("status")).toHaveTextContent("fastest of 2 comparable");
  expect(screen.getByText("Longcut")).toBeInTheDocument();
  expect(screen.getByText("Reference")).toBeInTheDocument();
  expect(screen.getAllByText("Live traffic (TomTom)").length).toBeGreaterThan(0);
  expect(screen.getByText("1 incident(s)")).toBeInTheDocument();
  expect(screen.getByText(/pulse forecast/i)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Hosur Road").closest("button"));
  expect(onSelect).toHaveBeenCalledWith("r2");
  fireEvent.click(screen.getByRole("button", { name: /navigation steps/ }));
  expect(screen.getByText("Head north")).toBeInTheDocument();
});

test("GPX parsing keeps only timestamped points", () => {
  const gpx = `<?xml version="1.0"?><gpx><trk><trkseg>
    <trkpt lat="12.9" lon="77.6"><time>2026-10-22T03:00:00Z</time></trkpt>
    <trkpt lat="12.91" lon="77.61"></trkpt>
  </trkseg></trk></gpx>`;
  expect(parseGpx(gpx)).toEqual([{ lat: 12.9, lon: 77.6, t: "2026-10-22T03:00:00Z" }]);
});
