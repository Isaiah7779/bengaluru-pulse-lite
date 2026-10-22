import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";
import { setToken } from "./api/client";

// Leaflet needs a real layout engine; the map is covered by browser testing.
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

const ME = [200, { id: 2, email: "u@x.in", display_name: "Ravi", role: "user", created_at: "2026-10-01T00:00:00Z" }];
const NOW = new Date().toISOString();
// TEST FIXTURES (response shapes), not real traffic data.
const SEGMENTS = (status = "fresh") => [
  200,
  {
    coverage_note: "Monitored sample points only.",
    stale_after_minutes: 90,
    segments: [
      { segment_id: 1, name: "Point A", lat: 12.9, lon: 77.5, status, observation: { congestion: "HEAVY", speed_ratio: 0.5, current_speed_kmph: 20, observed_at: NOW } },
      { segment_id: 2, name: "Point B", lat: 13.0, lon: 77.7, status, observation: { congestion: "FREE", speed_ratio: 0.95, current_speed_kmph: 40, observed_at: NOW } },
    ],
  },
];
const HISTORY = (id) => [
  200,
  {
    segment_id: id,
    observations: [
      { observed_at: "2026-10-22T04:00:00Z", speed_ratio: 0.6 },
      { observed_at: "2026-10-22T04:30:00Z", speed_ratio: 0.7 },
      { observed_at: "2026-10-22T05:00:00Z", speed_ratio: 0.8 },
    ],
  },
];
const COMMON = {
  "/v1/auth/me": ME,
  "/v1/incidents": [200, { total_active: 7, last_sweep_at: NOW, incidents: [] }],
  "/v1/weather/current": [200, { temperature_c: 24, description: "Overcast", time: NOW, attribution: "Open-Meteo" }],
  "/v1/forecast/models": [200, { models: [{ status: "baseline" }, { status: "candidate" }], routing_forecasts_enabled: false, note: "No model has passed evaluation." }],
};

beforeEach(() => {
  setToken("t");
  window.location.hash = "";
});

test("signed-in users land on Home, whose links lead to working pages", async () => {
  respond({ ...COMMON, "/v1/traffic/segments": SEGMENTS() });
  render(<App />);
  expect(await screen.findByRole("heading", { name: /Move smarter\. Understand Bengaluru\./ })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Explore the app/ })).toHaveAttribute("href", "#/navigate");
  const rail = screen.getByRole("navigation", { name: "Main" });
  for (const name of ["Home", "Navigate", "Traffic", "Insights", "Journal", "About", "My account"]) {
    expect(within(rail).getByRole("link", { name })).toBeInTheDocument();
  }
  expect(within(rail).queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  const dest = screen.getByRole("navigation", { name: "Bengaluru Pulse sections" });
  expect(within(dest).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["#/navigate", "#/traffic", "#/insights", "#/journal", "#/about"]);
  // Live metrics come from the API (fixture value), never from page text.
  expect(await screen.findByText("7")).toBeInTheDocument();
});

test("About shows no invented team members", async () => {
  window.location.hash = "#/about";
  respond({ ...COMMON });
  render(<App />);
  expect(await screen.findByRole("heading", { name: "The team behind Bengaluru Pulse" })).toBeInTheDocument();
  expect(screen.getByText(/will be introduced here once their details are confirmed/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Explore the app/ })).toHaveAttribute("href", "#/navigate");
  expect(screen.getByText(/Built-in accounts today/)).toBeInTheDocument();
});

test("Journal: empty state, honest notes status, and confirmed delete of the user's own journey", async () => {
  window.location.hash = "#/journal";
  let trips = [];
  respond({
    ...COMMON,
    "/v1/me/trips": () => [200, trips],
    "DELETE /v1/me/trips/5": () => {
      trips = [];
      return [204, null];
    },
  });
  const { unmount } = render(<App />);
  expect(await screen.findByText(/No saved journeys yet/)).toBeInTheDocument();
  expect(screen.getByText(/Notes are not available on this server yet/)).toBeInTheDocument();
  unmount();

  trips = [{ id: 5, origin_label: "MG Road", destination_label: "Koramangala", vehicle: "car", preference: "fastest", created_at: NOW, chosen_route: { eta_s: 1500, distance_m: 7000, eta_basis: "traffic_live" } }];
  render(<App />);
  expect(await screen.findByText("MG Road → Koramangala")).toBeInTheDocument();
  window.confirm = jest.fn(() => false);
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  expect(global.fetch.mock.calls.some(([, o]) => o?.method === "DELETE")).toBe(false);
  window.confirm = jest.fn(() => true);
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  expect(await screen.findByText("Journey deleted.")).toBeInTheDocument();
  expect(global.fetch.mock.calls.some(([u, o]) => o?.method === "DELETE" && u.endsWith("/v1/me/trips/5"))).toBe(true);
});

test("Insights uses stored data and handles failed, empty and stale responses", async () => {
  window.location.hash = "#/insights";
  respond({
    ...COMMON,
    "/v1/traffic/segments": [503, { error: { code: "db_unavailable", message: "Database unavailable" } }],
    "/v1/weather/areas": [200, { areas: [], attribution: "Open-Meteo" }],
  });
  const { unmount } = render(<App />);
  expect(await screen.findByText(/Traffic overview could not be loaded: Database unavailable/)).toBeInTheDocument();
  expect(await screen.findByText("No weather has been collected yet.")).toBeInTheDocument();
  expect(screen.getByText(/Not used yet\. No model has passed evaluation\./)).toBeInTheDocument();
  unmount();

  respond({
    ...COMMON,
    "/v1/traffic/segments": SEGMENTS("stale"),
    "/v1/traffic/segments/1/history": HISTORY(1),
    "/v1/traffic/segments/2/history": HISTORY(2),
    "/v1/weather/areas": [200, { areas: [{ area: "Central", temperature_c: 23, precipitation_mm: 0.4, observed_at: NOW }], attribution: "Open-Meteo" }],
  });
  render(<App />);
  expect(await screen.findByText(/No reading is fresher than 90 minutes/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText(/Average of 6 stored readings/)).toBeInTheDocument());
  expect(screen.getByText(/rain reported in Central/)).toBeInTheDocument();
});
