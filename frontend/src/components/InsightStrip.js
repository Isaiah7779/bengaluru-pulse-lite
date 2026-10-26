import { useEffect, useState } from "react";
import { api } from "../api/client";
import { BENGALURU_CENTER, CONGESTION_COLORS } from "../config";
import { ago, BASIS_LABEL, km, minutes } from "../format";
import CityArt from "./CityArt";
import Icon from "./Icons";

const LEVELS = ["FREE", "MODERATE", "HEAVY", "SEVERE", "CLOSED"];
const REFRESH_MS = 5 * 60 * 1000;

function useLive(loader) {
  const [state, setState] = useState({ data: null, error: null });
  useEffect(() => {
    let alive = true;
    const load = () =>
      loader()
        .then((data) => alive && setState({ data, error: null }))
        .catch((err) => alive && setState({ data: null, error: err.message }));
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [loader]);
  return state;
}

const loadSegments = () => api("/v1/traffic/segments");
const loadIncidents = () => api("/v1/incidents", { params: { limit: 1 } });
const loadWeather = () => api("/v1/weather/current", { params: { lat: BENGALURU_CENTER[0], lon: BENGALURU_CENTER[1] } });

function Card({ label, icon, children, className = "", loading }) {
  return (
    <article className={`insight ${className} ${loading ? "is-loading" : ""}`}>
      <div className="insight-label">
        {icon && <Icon name={icon} size={16} />}
        <span>{label}</span>
      </div>
      {children}
    </article>
  );
}

export function TrafficCard() {
  const { data, error } = useLive(loadSegments);
  if (error) return <Card label="Live traffic" icon="pulse"><p className="insight-sub">Traffic data unavailable right now.</p></Card>;
  if (!data) return <Card label="Live traffic" icon="pulse" loading><div className="skeleton" /></Card>;
  const fresh = data.segments.filter((s) => s.status === "fresh");
  const counts = Object.fromEntries(LEVELS.map((l) => [l, fresh.filter((s) => s.observation?.congestion === l).length]));
  const latest = fresh.map((s) => s.observation.observed_at).sort().pop();
  return (
    <Card label="Live traffic" icon="pulse">
      <div className="insight-value">
        {fresh.length}
        <small>/{data.segments.length}</small>
      </div>
      <p className="insight-sub">monitored points fresh · {latest ? ago(latest) : "no recent data"}</p>
      <div className="sev-bar" role="img" aria-label={LEVELS.map((l) => `${counts[l]} ${l.toLowerCase()}`).join(", ")}>
        {LEVELS.filter((l) => counts[l]).map((l) => (
          <span key={l} style={{ flex: counts[l], background: CONGESTION_COLORS[l] }} title={`${counts[l]} ${l.toLowerCase()}`} />
        ))}
      </div>
      <p className="insight-fine">Sample points on major corridors, not city-wide coverage.</p>
    </Card>
  );
}

export function IncidentCard() {
  const { data, error } = useLive(loadIncidents);
  if (error) return <Card label="Road incidents" icon="alert"><p className="insight-sub">Incident feed unavailable.</p></Card>;
  if (!data) return <Card label="Road incidents" icon="alert" loading><div className="skeleton" /></Card>;
  return (
    <Card label="Road incidents" icon="alert">
      <div className="insight-value">{data.total_active}</div>
      <p className="insight-sub">active · refreshed {ago(data.last_sweep_at)}</p>
      <p className="insight-fine">TomTom incidents, hourly sweep</p>
    </Card>
  );
}

export function WeatherCard() {
  const { data, error } = useLive(loadWeather);
  if (error) return <Card label="Bengaluru weather" icon="cloud"><p className="insight-sub">Weather unavailable.</p></Card>;
  if (!data) return <Card label="Bengaluru weather" icon="cloud" loading><div className="skeleton" /></Card>;
  return (
    <Card label="Bengaluru weather" icon={data.wet ? "rain" : "cloud"}>
      <div className="insight-value">
        {data.temperature_c != null ? Math.round(data.temperature_c) : "–"}
        <small>°C</small>
      </div>
      <p className="insight-sub">
        {data.description}
        {data.precipitation_mm ? ` · ${data.precipitation_mm} mm` : ""} · {ago(data.time)}
      </p>
      <p className="insight-fine">{data.attribution}</p>
    </Card>
  );
}

function RouteCard({ route }) {
  if (!route) {
    return (
      <Card label="Route preview" icon="route" className="insight--dark">
        <p className="insight-quote">Plan a journey to see its time, distance and traffic here.</p>
      </Card>
    );
  }
  return (
    <Card label="Route preview" icon="route" className="insight--dark">
      <div className="insight-value">{minutes(route.eta_s)}</div>
      <p className="insight-sub">
        {km(route.distance_m)} · {BASIS_LABEL[route.eta_basis]}
      </p>
      <p className="insight-fine">
        {route.traffic ? `TomTom delay ${minutes(route.traffic.traffic_delay_s)}` : route.traffic_note || "No traffic timing for this route"}
        {route.incidents.length ? ` · ${route.incidents.length} incident(s) on route` : ""}
      </p>
    </Card>
  );
}

function ExploreCard({ onShowTraffic }) {
  return (
    <article className="insight insight--art">
      <CityArt />
      <div className="insight-art-copy">
        <div className="insight-label">
          <Icon name="spark" size={16} />
          <span>Explore Bengaluru</span>
        </div>
        <p className="insight-art-title">See the corridors we watch.</p>
        <div className="insight-actions">
          <button type="button" className="chip-btn" onClick={onShowTraffic}>
            Show on map
          </button>
          <a className="chip-btn" href="#/traffic">
            Traffic <Icon name="arrow" size={14} />
          </a>
        </div>
      </div>
    </article>
  );
}

export default function InsightStrip({ selectedRoute, onShowTraffic }) {
  return (
    <section className="insights" aria-label="Live city insights">
      <TrafficCard />
      <IncidentCard />
      <WeatherCard />
      <RouteCard route={selectedRoute} />
      <ExploreCard onShowTraffic={onShowTraffic} />
    </section>
  );
}
