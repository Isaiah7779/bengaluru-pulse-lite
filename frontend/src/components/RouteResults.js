import { useState } from "react";
import { ROUTE_COLORS } from "../config";
import { BASIS_LABEL, CLASS_LABEL, ago, clock, km, minutes, signedDelta } from "../format";

function Badge({ kind }) {
  return <span className={`badge badge-${kind}`}>{CLASS_LABEL[kind] || kind}</span>;
}

function SourceList({ sources }) {
  return (
    <ul className="sources">
      {sources.map((s) => (
        <li key={s.name} className={`src src-${s.status}`}>
          <span className="src-name">{s.name.replace(/_/g, " ")}</span>
          <span className="src-status">{s.status.replace(/_/g, " ")}</span>
          {s.detail && <span className="src-detail">{s.detail}</span>}
          {s.as_of && <span className="src-detail">as of {ago(s.as_of)}</span>}
        </li>
      ))}
    </ul>
  );
}

function RouteCard({ route, selected, onSelect }) {
  const c = route.classification;
  return (
    <button
      type="button"
      className={`route-card ${selected ? "selected" : ""}`}
      onClick={() => onSelect(route.id)}
      aria-pressed={selected}
      style={{ borderLeftColor: ROUTE_COLORS[(route.rank - 1) % ROUTE_COLORS.length] }}
    >
      <div className="rc-top">
        <span className="rc-eta">{minutes(route.eta_s)}</span>
        <span className="rc-dist">{km(route.distance_m)}</span>
        {route.recommended && <span className="badge badge-rec">Recommended</span>}
        <Badge kind={c.type} />
      </div>
      <div className="rc-summary">{route.summary || "Unnamed roads"}</div>
      <div className="rc-meta">
        <span title="How this ETA was obtained">{BASIS_LABEL[route.eta_basis]}</span>
        {route.traffic && route.eta_basis !== "free_flow" && <span>delay {minutes(route.traffic.traffic_delay_s)}</span>}
        {route.incidents.length > 0 && <span className="warn">{route.incidents.length} incident(s)</span>}
        {!route.comparable && <span className="warn">not traffic-timed</span>}
      </div>
      {!route.is_reference && c.type !== "unclassified" && (
        <div className="rc-delta">
          vs reference: {signedDelta(c.distance_diff_m / 1000, "km")}, {signedDelta(c.time_diff_s / 60, "min")}
        </div>
      )}
    </button>
  );
}

function RouteDetail({ route }) {
  const [showSteps, setShowSteps] = useState(false);
  const t = route.traffic;
  return (
    <div className="route-detail">
      <h3>Why this route</h3>
      <ul className="explanation">
        {route.explanation.map((line, i) => (
          <li key={i}>{line}</li>
        ))}
      </ul>
      {t && (
        <div className="kv">
          <div>
            <span>Traffic ETA</span>
            <b>{minutes(t.eta_s)}</b>
          </div>
          <div>
            <span>Free-flow</span>
            <b>{minutes(t.no_traffic_s ?? route.free_flow_duration_s)}</b>
          </div>
          {t.historic_s != null && (
            <div>
              <span>Typical (TomTom)</span>
              <b>{minutes(t.historic_s)}</b>
            </div>
          )}
          <div>
            <span>Arrive</span>
            <b>{clock(t.arrive_at)}</b>
          </div>
        </div>
      )}
      {route.monitored_segments.length > 0 && (
        <>
          <h4>Monitored points on this route</h4>
          <ul className="compact">
            {route.monitored_segments.map((s) => (
              <li key={s.segment_id}>
                {s.name}:{" "}
                {s.congestion ? (
                  <b className={`cg-${s.congestion}`}>
                    {s.congestion} ({Math.round(s.speed_ratio * 100)}% of free-flow, {ago(s.observed_at)})
                  </b>
                ) : (
                  <span className="muted">no fresh observation</span>
                )}
                {s.forecast && (
                  <span className="muted">
                    {" "}
                    · forecast {Math.round(s.forecast.predicted_speed_ratio * 100)}% ({s.forecast.horizon}, test MAE {s.forecast.test_mae})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
      {route.incidents.length > 0 && (
        <>
          <h4>Incidents on this route</h4>
          <ul className="compact">
            {route.incidents.map((i) => (
              <li key={i.id}>
                <b>{i.category.replace(/_/g, " ")}</b>
                {i.road ? ` – ${i.road}` : ""}
                {i.description ? `: ${i.description}` : ""} <span className="muted">({i.source})</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {route.steps.length > 0 && (
        <>
          <button type="button" className="link-btn" onClick={() => setShowSteps((v) => !v)} aria-expanded={showSteps}>
            {showSteps ? "Hide" : "Show"} {route.steps.length} navigation steps
          </button>
          {showSteps && (
            <ol className="steps">
              {route.steps.map((s, i) => (
                <li key={i}>
                  <span>{s.instruction}</span>
                  <span className="muted">{km(s.distance_m)}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
}

export default function RouteResults({ result, selectedId, onSelect }) {
  const selected = result.routes.find((r) => r.id === selectedId) || result.routes[0];
  return (
    <section className="results" aria-label="Route results">
      <div className="recommendation" role="status">
        <b>{result.recommendation}</b>
        {result.preference_note && <div className="note">{result.preference_note}</div>}
        <div className="muted small">
          Compared on: {BASIS_LABEL[result.comparison_basis]} · departure {result.departure_mode === "now" ? "now" : clock(result.depart_at)} ·{" "}
          {result.candidates_considered} candidates considered
        </div>
      </div>
      {result.warnings.map((w, i) => (
        <div key={i} className="warning">
          {w}
        </div>
      ))}
      {result.vehicle_profile.profile_status !== "dedicated" && <div className="warning">{result.vehicle_profile.notes}</div>}
      <div className="route-list">
        {result.routes.map((r) => (
          <RouteCard key={r.id} route={r} selected={r.id === selected.id} onSelect={onSelect} />
        ))}
      </div>
      <p className="muted small">{result.reference_description}</p>
      <RouteDetail route={selected} />
      {result.weather && (
        <div className="weather">
          <b>Weather {result.weather.kind === "forecast" ? "forecast" : "now"}:</b> {result.weather.description}
          {result.weather.temperature_c != null && `, ${Math.round(result.weather.temperature_c)}°C`}
          {result.weather.precipitation_mm ? `, ${result.weather.precipitation_mm} mm rain` : ""}
          <span className="muted small"> — {result.weather.attribution}</span>
        </div>
      )}
      <details className="sources-box">
        <summary>Data sources for this result</summary>
        <SourceList sources={result.data_sources} />
      </details>
    </section>
  );
}
