import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import HeroArt from "../components/HeroArt";
import Icon from "../components/Icons";
import InsightStrip from "../components/InsightStrip";
import MapView from "../components/MapView";
import PlaceSearch from "../components/PlaceSearch";
import RouteResults from "../components/RouteResults";
import * as personal from "../data/personal";

const PREFERENCES = [
  ["fastest", "Fastest"],
  ["shortest", "Shortest"],
  ["least_traffic_now", "Least traffic now"],
  ["least_traffic_predicted", "Least predicted traffic"],
  ["balanced", "Balanced"],
];
const VEHICLE_LABEL = { car: "Car", motorcycle: "Motorcycle", bicycle: "Bicycle", walk: "Walk" };
const VEHICLE_ICON = { car: "car", motorcycle: "moto", bicycle: "bike", walk: "walk" };
const LAYERS = [
  ["traffic", "Monitored traffic"],
  ["incidents", "Incidents"],
  ["shortcuts", "Verified shortcuts"],
];

// Wide screens dock the planner over the map; narrower ones stack it below the map.
const DOCKED_QUERY = "(min-width: 1200px)";
function useDocked() {
  const get = () => Boolean(window.matchMedia && window.matchMedia(DOCKED_QUERY).matches);
  const [docked, setDocked] = useState(get);
  useEffect(() => {
    if (!window.matchMedia) return undefined;
    const mq = window.matchMedia(DOCKED_QUERY);
    const on = () => setDocked(mq.matches);
    mq.addEventListener ? mq.addEventListener("change", on) : mq.addListener(on);
    return () => (mq.removeEventListener ? mq.removeEventListener("change", on) : mq.removeListener(on));
  }, []);
  return docked;
}

function localInputValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function NavigatePage() {
  const { user, mode } = useAuth();
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
  const [favorites, setFavorites] = useState([]);
  const pendingAvoid = useRef(null);
  const docked = useDocked();

  // Personal defaults and saved places (Firestore) for Firebase accounts.
  useEffect(() => {
    if (mode !== "firebase") return;
    personal
      .getPreferences()
      .then((p) => {
        if (!p) return;
        if (p.vehicle) setVehicle(p.vehicle);
        if (p.routePreference) setPreference(p.routePreference);
        if (p.avoid) pendingAvoid.current = p.avoid;
      })
      .catch(() => {});
    personal.listFavorites().then(setFavorites).catch(() => setFavorites([]));
  }, [mode]);

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
    if (pendingAvoid.current && avoidOptions.includes(pendingAvoid.current)) {
      setAvoid(pendingAvoid.current);
      pendingAvoid.current = null;
      return;
    }
    if (!avoidOptions.includes(avoid)) setAvoid("");
  }, [avoidOptions, avoid]);

  function pickFavorite(f) {
    const place = { lat: f.lat, lon: f.lon, label: f.label };
    if (!origin) setOrigin(place);
    else setDestination(place);
    setResult(null);
  }

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
      // Docked: results appear inside the floating panel. Stacked: bring them into view.
      if (!docked) {
        setTimeout(() => document.querySelector(".results")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      } else {
        setTimeout(() => document.querySelector(".planner-dock")?.scrollTo({ top: document.querySelector(".planner")?.offsetHeight || 0, behavior: "smooth" }), 50);
      }
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

  const selectedRoute = result ? result.routes.find((r) => r.id === selectedId) : null;

  return (
    <div className="nav-page">
      <section className="nav-stage">
        <div className="nav-hero">
          <header className="hero">
            <p className="eyebrow">Bengaluru · Live city navigation</p>
            <h1 className="hero-title">
              Move smarter. <em>Bengaluru.</em>
            </h1>
            <p className="hero-copy">Live traffic. Smarter routes. Clearer decisions. A calmer city, together.</p>
            <ul className="hero-tags" aria-label="What Bengaluru Pulse uses">
              <li>OSRM routes</li>
              <li>TomTom traffic</li>
              <li>Open-Meteo weather</li>
            </ul>
          </header>
          <HeroArt />
        </div>

        <div className={`nav-map ${docked ? "is-docked" : ""}`}>
          <div className="map-frame">
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
              fitPaddingLeft={docked ? 420 : 40}
            />
            <div className="map-layers" aria-label="Map layers">
              <Icon name="layers" size={16} />
              {LAYERS.map(([key, label]) => (
                <label key={key} className={`layer-pill ${layers[key] ? "on" : ""}`}>
                  <input type="checkbox" checked={layers[key]} onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))} /> {label}
                </label>
              ))}
            </div>
            {(result || layers.traffic || layers.incidents) && (
              <div className="map-legend" aria-label="Map legend">
                {result && (
                  <span>
                    <i className="lg-line lg-selected" /> Selected route
                  </span>
                )}
                {result && result.routes.length > 1 && (
                  <span>
                    <i className="lg-line lg-alt" /> Alternatives
                  </span>
                )}
                {layers.traffic && (
                  <>
                    <span>
                      <i className="lg-dot sev-free" /> Free
                    </span>
                    <span>
                      <i className="lg-dot sev-moderate" /> Moderate
                    </span>
                    <span>
                      <i className="lg-dot sev-heavy" /> Heavy
                    </span>
                  </>
                )}
                {layers.incidents && (
                  <span>
                    <i className="lg-dot sev-severe" /> Incident
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="planner-dock">
          <form onSubmit={plan} className="route-form planner" aria-label="Plan a route">
            <div className="planner-head">
              <span className="eyebrow">Plan a journey</span>
              <span className="planner-step" aria-hidden="true">
                01
              </span>
            </div>
            <div className="od-group">
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
              <button type="button" className="swap-btn" onClick={swap} aria-label="Swap start and destination" title="Swap">
                <Icon name="swap" size={18} />
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
            </div>
            {favorites.length > 0 && (
              <div className="fav-chips" aria-label="Saved places">
                <span className="field-label">Saved places</span>
                {favorites.slice(0, 6).map((f) => (
                  <button type="button" key={f.id} className="fav-chip" onClick={() => pickFavorite(f)} title={f.detail || f.label}>
                    <Icon name="pin" size={14} /> {f.label}
                  </button>
                ))}
              </div>
            )}
            {picking && (
              <div className="hint info" role="status">
                Tap the map to set the {picking === "origin" ? "start" : "destination"}.
              </div>
            )}

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
                  <Icon name={VEHICLE_ICON[v.vehicle]} size={18} />
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

            <button type="submit" className="primary plan-btn" disabled={loading}>
              {loading ? (
                <>
                  <span className="spinner" aria-hidden="true" /> Finding routes…
                </>
              ) : (
                <>
                  Find routes <Icon name="arrow" size={18} />
                </>
              )}
            </button>
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
          </form>

          {result && <RouteResults result={result} selectedId={selectedId} onSelect={setSelectedId} />}
          {!result && !loading && (
            <p className="muted small intro">
              Routes come from OpenStreetMap via OSRM, timed with TomTom traffic where available. Every figure shows its source; nothing is
              simulated.
            </p>
          )}
          </div>
        </div>
      </section>

      <InsightStrip selectedRoute={selectedRoute} onShowTraffic={() => setLayers((l) => ({ ...l, traffic: true }))} />
    </div>
  );
}
