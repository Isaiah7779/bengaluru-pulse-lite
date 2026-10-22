import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import Icon from "../components/Icons";
import { CONGESTION_COLORS } from "../config";
import { ago, clock } from "../format";

function SegmentHistory({ segment }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    setData(null);
    setError(null);
    api(`/v1/traffic/segments/${segment.segment_id}/history`, { params: { hours: 72 } })
      .then((r) => setData(r.observations.map((o) => ({ t: new Date(o.observed_at).getTime(), ratio: Math.round(o.speed_ratio * 100), speed: o.current_speed_kmph }))))
      .catch((e) => setError(e.message));
  }, [segment.segment_id]);
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <div className="skeleton" style={{ height: 220 }} />;
  if (data.length < 2) return <div className="muted">Not enough observations yet for a chart ({data.length} so far).</div>;
  return (
    <div className="chart" aria-label={`Speed history for ${segment.name}`}>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={(t) => clock(new Date(t).toISOString())} tick={{ fontSize: 11 }} stroke="var(--grid)" />
          <YAxis domain={[0, 120]} tick={{ fontSize: 11 }} unit="%" width={44} stroke="var(--grid)" />
          <ReferenceLine y={100} stroke="var(--warm-gray)" strokeDasharray="4 4" />
          <Tooltip
            labelFormatter={(t) => clock(new Date(t).toISOString())}
            formatter={(v, n) => (n === "ratio" ? [`${v}% of free-flow`, "Speed"] : [v, n])}
            contentStyle={{ background: "#17131C", border: "none", borderRadius: 10, color: "#FCF8F1", fontSize: 12 }}
            itemStyle={{ color: "#FCF8F1" }}
          />
          <Line type="monotone" dataKey="ratio" stroke="#6338D8" dot={false} strokeWidth={2.5} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="muted small">Collected TomTom observations, last 72 h ({data.length} points). Dashed line = free-flow speed.</div>
    </div>
  );
}

function Ratio({ ratio, congestion }) {
  const pct = Math.round(ratio * 100);
  return (
    <div className="ratio">
      <div className="ratio-track">
        <i style={{ width: `${Math.min(pct, 100)}%`, background: CONGESTION_COLORS[congestion] || "var(--sev-unknown)" }} />
      </div>
      <b>{pct}%</b>
    </div>
  );
}

export default function TrafficPage() {
  const [segments, setSegments] = useState(null);
  const [note, setNote] = useState("");
  const [incidents, setIncidents] = useState(null);
  const [weather, setWeather] = useState(null);
  const [models, setModels] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      api("/v1/traffic/segments"),
      api("/v1/incidents", { params: { limit: 50 } }),
      api("/v1/weather/areas"),
      api("/v1/forecast/models"),
    ])
      .then(([s, i, w, m]) => {
        setSegments(s.segments);
        setNote(s.coverage_note);
        setIncidents(i);
        setWeather(w);
        setModels(m);
      })
      .catch((e) => setError(e.message));
  }, []);

  const head = (
    <header className="page-head">
      <div>
        <p className="eyebrow">Live city dashboard</p>
        <h2 className="page-title">
          Bengaluru, <em>in motion.</em>
        </h2>
      </div>
      <p className="page-lede">
        What our collector has actually measured: monitored corridor points from TomTom, active road incidents and Open-Meteo weather. {note}
      </p>
    </header>
  );

  if (error)
    return (
      <div className="page">
        {head}
        <div className="error-box">{error}</div>
      </div>
    );
  if (!segments)
    return (
      <div className="page">
        {head}
        <p className="muted">Loading traffic data…</p>
      </div>
    );

  const sorted = [...segments].sort((a, b) => (a.observation?.speed_ratio ?? 9) - (b.observation?.speed_ratio ?? 9));
  const freshList = segments.filter((s) => s.status === "fresh");
  const congested = freshList.filter((s) => ["HEAVY", "SEVERE", "CLOSED"].includes(s.observation?.congestion)).length;
  const latest = freshList.map((s) => s.observation.observed_at).sort().pop();

  return (
    <div className="page">
      {head}

      <div className="stat-row">
        <div className="stat">
          <p className="eyebrow">Monitored points</p>
          <b>
            {freshList.length}
            <small>/{segments.length}</small>
          </b>
          <span>fresh · latest {latest ? ago(latest) : "none yet"}</span>
        </div>
        <div className="stat">
          <p className="eyebrow">Heavy or worse</p>
          <b>{congested}</b>
          <span>of the fresh points right now</span>
        </div>
        <div className="stat">
          <p className="eyebrow">Road incidents</p>
          <b>{incidents?.total_active ?? "–"}</b>
          <span>active · swept {ago(incidents?.last_sweep_at)}</span>
        </div>
        <div className="stat stat--dark">
          <p className="eyebrow">Pulse forecasts in routing</p>
          <b>{models?.routing_forecasts_enabled ? "On" : "Off"}</b>
          <span>{models?.routing_forecasts_enabled ? "promoted model in use" : "no model has met the promotion bar"}</span>
        </div>
      </div>

      {models && !models.routing_forecasts_enabled && (
        <div className="forecast-note">
          <Icon name="spark" size={22} />
          <div>
            <b>About predictions</b>
            <p>
              {models.note} Where a route shows a "typical" time, that figure is TomTom's own historic estimate, not a Bengaluru Pulse
              forecast.
            </p>
          </div>
        </div>
      )}

      <div className="two-col">
        <section className="panel">
          <div className="panel-head">
            <h3>Monitored points</h3>
            <span className="eyebrow">Slowest first</span>
          </div>
          <div className="table-wrap">
            <table className="table seg-table">
              <thead>
                <tr>
                  <th>Point</th>
                  <th>Status</th>
                  <th>Speed</th>
                  <th>vs free-flow</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((s) => (
                  <tr
                    key={s.segment_id}
                    className={`clickable ${selected?.segment_id === s.segment_id ? "sel" : ""}`}
                    onClick={() => setSelected(s)}
                    tabIndex={0}
                    aria-selected={selected?.segment_id === s.segment_id}
                    onKeyDown={(e) => e.key === "Enter" && setSelected(s)}
                  >
                    <td>
                      <b>{s.name}</b>
                    </td>
                    <td>
                      <span className={`sev-chip ${s.observation?.congestion || ""}`}>{s.observation ? s.observation.congestion : "unknown"}</span>
                    </td>
                    <td>{s.observation ? `${s.observation.current_speed_kmph} km/h` : "–"}</td>
                    <td>{s.observation ? <Ratio ratio={s.observation.speed_ratio} congestion={s.observation.congestion} /> : "–"}</td>
                    <td>
                      {s.observation ? ago(s.observation.observed_at) : "never"}
                      {s.status !== "fresh" && <div className="fresh-tag stale">{s.status.replace("_", " ")}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div>
          <section className="panel">
            <div className="panel-head">
              <h3>{selected ? selected.name : "Point history"}</h3>
              <Icon name="clock" size={18} />
            </div>
            {selected ? <SegmentHistory segment={selected} /> : <p className="muted">Select a point to see its collected history.</p>}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h3>Weather</h3>
              <span className="eyebrow">Open-Meteo</span>
            </div>
            {weather?.areas?.length ? (
              <div className="weather-grid">
                {weather.areas.map((a) => (
                  <div className="wx" key={a.area}>
                    <span className="wx-area">{a.area}</span>
                    <b>{a.temperature_c != null ? `${Math.round(a.temperature_c)}°` : "–"}</b>
                    <span>
                      {a.precipitation_mm ? `${a.precipitation_mm} mm rain · ` : ""}
                      {ago(a.observed_at)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">No weather collected yet.</p>
            )}
            <p className="muted small">{weather?.attribution}</p>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h3>Latest incidents</h3>
              <span className="eyebrow">{incidents?.total_active ?? 0} active</span>
            </div>
            {(incidents?.incidents || []).length ? (
              <ul className="feed">
                {incidents.incidents.slice(0, 12).map((i) => (
                  <li key={i.id}>
                    <span className="feed-dot" aria-hidden="true" />
                    <div>
                      <div className="feed-title">{i.category.replace(/_/g, " ")}</div>
                      {i.road_from && (
                        <div className="feed-road">
                          {i.road_from}
                          {i.road_to ? ` → ${i.road_to}` : ""}
                        </div>
                      )}
                    </div>
                    <div className="feed-meta">
                      {i.source}
                      {i.delay_s ? (
                        <>
                          <br />+{Math.round(i.delay_s / 60)} min
                        </>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No active incidents reported.</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
