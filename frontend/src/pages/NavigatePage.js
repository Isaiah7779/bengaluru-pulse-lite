import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import MapView from "../components/MapView";
import PlaceSearch from "../components/PlaceSearch";
import RouteResults from "../components/RouteResults";

const PREFERENCES = [
  ["fastest", "Fastest"],
  ["shortest", "Shortest"],
  ["least_traffic_now", "Least traffic now"],
  ["least_traffic_predicted", "Least predicted traffic"],
  ["balanced", "Balanced"],
];
const VEHICLE_LABEL = { car: "Car", motorcycle: "Motorcycle", bicycle: "Bicycle", walk: "Walk" };

function localInputValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function NavigatePage() {
  const { user } = useAuth();
  const [origin, setOrigin] = useState(null);
  const [destination, setDestination] = useState(null);
  const [vehicles, setVehicles] = useState([]);
  const [vehicle, setVehicle] = useState("car");
  const [preference, setPreference] = useState("fastest");
  const [departMode, setDepartMode] = useState("now");
  const [departAt, setDepartAt] = useState(() => localInputValue(new Date(Date.now() + 3600 * 1000)));
  const [avoid, setAvoid] = useState("");
  const [saveTrip, setSaveTrip] = useState(false);
  const [picking, setPicking] = useState(null);
  const [result, setResult] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [layers, setLayers] = useState({ traffic: false, incidents: false, shortcuts: false });
  const [segments, setSegments] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [shortcuts, setShortcuts] = useState([]);

  useEffect(() => {
    api("/v1/vehicles")
      .then((r) => setVehicles(r.vehicles))
      .catch(() => setVehicles([]));
  }, []);

  useEffect(() => {
    if (layers.traffic) api("/v1/traffic/segments").then((r) => setSegments(r.segments)).catch(() => setSegments([]));
  }, [layers.traffic]);
  useEffect(() => {
    if (layers.incidents) api("/v1/incidents", { params: { limit: 500 } }).then((r) => setIncidents(r.incidents)).catch(() => setIncidents([]));
  }, [layers.incidents]);
  useEffect(() => {
    if (layers.shortcuts) api("/v1/community/shortcuts").then((r) => setShortcuts(r.shortcuts)).catch(() => setShortcuts([]));
  }, [layers.shortcuts]);

  const vehicleInfo = useMemo(() => vehicles.find((v) => v.vehicle === vehicle), [vehicles, vehicle]);
  const avoidOptions = useMemo(() => vehicleInfo?.avoid_options || [], [vehicleInfo]);

  useEffect(() => {
    if (!avoidOptions.includes(avoid)) setAvoid("");
  }, [avoidOptions, avoid]);

  const onPick = useCallback(
    async (point) => {
      const target = picking;
      setPicking(null);
      let label = `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`;
      try {
        const rev = await api("/v1/geocode/reverse", { params: point });
        label = rev.label;
      } catch {
        /* keep coordinate label */
      }
      const place = { ...point, label };
      if (target === "origin") setOrigin(place);
      else setDestination(place);
    },
    [picking]
  );

  async function plan(e) {
    e.preventDefault();
    if (!origin || !destination) {
      setError("Choose both a start and a destination.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const body = {
        origin,
        destination,
        vehicle,
        preference,
        avoid: avoid ? [avoid] : [],
        max_routes: 5,
        save_trip: Boolean(user && saveTrip),
      };
      if (departMode === "later") body.depart_at = new Date(departAt).toISOString();
      const res = await api("/v1/routes", { method: "POST", body });
      setResult(res);
      setSelectedId(res.recommended_route_id);
    } catch (err) {
      setResult(null);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function swap() {
    setOrigin(destination);
    setDestination(origin);
    setResult(null);
  }

  return (
    <div className="navigate">
      <aside className="sidebar">
        <form onSubmit={plan} className="route-form" aria-label="Plan a route">
          <PlaceSearch
            label="From"
            value={origin}
            onChange={(p) => {
              setOrigin(p);
              setResult(null);
            }}
            onPickOnMap={() => setPicking(picking === "origin" ? null : "origin")}
            picking={picking === "origin"}
            near={destination}
          />
          <button type="button" className="swap-btn" onClick={swap} aria-label="Swap start and destination">
            ⇅
          </button>
          <PlaceSearch
            label="To"
            value={destination}
            onChange={(p) => {
              setDestination(p);
              setResult(null);
            }}
            onPickOnMap={() => setPicking(picking === "destination" ? null : "destination")}
            picking={picking === "destination"}
            near={origin}
          />
          {picking && <div className="hint info">Click on the map to set the {picking === "origin" ? "start" : "destination"}.</div>}

          <fieldset className="vehicles">
            <legend className="field-label">Travel mode</legend>
            {(vehicles.length ? vehicles : Object.keys(VEHICLE_LABEL).map((v) => ({ vehicle: v, available: true }))).map((v) => (
              <label key={v.vehicle} className={`chip ${vehicle === v.vehicle ? "on" : ""} ${v.available === false ? "disabled" : ""}`}>
                <input
                  type="radio"
                  name="vehicle"
                  value={v.vehicle}
                  checked={vehicle === v.vehicle}
                  disabled={v.available === false}
                  onChange={() => setVehicle(v.vehicle)}
                />
                {VEHICLE_LABEL[v.vehicle]}
              </label>
            ))}
          </fieldset>
          {vehicleInfo && vehicleInfo.profile_status !== "dedicated" && <div className="hint">{vehicleInfo.notes}</div>}
          {vehicleInfo && vehicleInfo.available === false && <div className="hint error">This mode's routing graph is not running.</div>}

          <div className="row2">
            <label>
              <span className="field-label">Preference</span>
              <select value={preference} onChange={(e) => setPreference(e.target.value)}>
                {PREFERENCES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="field-label">Avoid</span>
              <select value={avoid} onChange={(e) => setAvoid(e.target.value)} disabled={!avoidOptions.length}>
                <option value="">Nothing</option>
                {avoidOptions.map((a) => (
                  <option key={a} value={a}>
                    {a === "motorway" ? "Expressways" : a === "toll" ? "Toll roads" : "Ferries"}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="row2">
            <label>
              <span className="field-label">Departure</span>
              <select value={departMode} onChange={(e) => setDepartMode(e.target.value)}>
                <option value="now">Leave now</option>
                <option value="later">Leave at…</option>
              </select>
            </label>
            {departMode === "later" && (
              <label>
                <span className="field-label">Time</span>
                <input
                  type="datetime-local"
                  value={departAt}
                  min={localInputValue(new Date())}
                  max={localInputValue(new Date(Date.now() + 7 * 86400 * 1000))}
                  onChange={(e) => setDepartAt(e.target.value)}
                />
              </label>
            )}
          </div>

          {user && (
            <label className="check">
              <input type="checkbox" checked={saveTrip} onChange={(e) => setSaveTrip(e.target.checked)} /> Save to my trip history
            </label>
          )}

          <button type="submit" className="primary" disabled={loading}>
            {loading ? "Finding routes…" : "Find routes"}
          </button>
          {error && (
            <div className="error-box" role="alert">
              {error}
            </div>
          )}
        </form>

        <div className="layers" aria-label="Map layers">
          {[
            ["traffic", "Monitored traffic"],
            ["incidents", "Incidents"],
            ["shortcuts", "Verified shortcuts"],
          ].map(([key, label]) => (
            <label key={key} className="check">
              <input type="checkbox" checked={layers[key]} onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))} /> {label}
            </label>
          ))}
        </div>

        {result && <RouteResults result={result} selectedId={selectedId} onSelect={setSelectedId} />}
        {!result && !loading && (
          <p className="muted small intro">
            Routes come from OpenStreetMap via OSRM, timed with TomTom traffic where available. Every figure shows its source; nothing is
            simulated.
          </p>
        )}
      </aside>
      <main className="map-wrap">
        <MapView
          routes={result ? result.routes : []}
          selectedId={selectedId}
          onSelect={setSelectedId}
          origin={origin}
          destination={destination}
          picking={picking}
          onPick={onPick}
          segments={layers.traffic ? segments : []}
          incidents={layers.incidents ? incidents : []}
          shortcuts={layers.shortcuts ? shortcuts : []}
        />
      </main>
    </div>
  );
}
