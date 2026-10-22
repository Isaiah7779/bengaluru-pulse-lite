import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { ago, clock } from "../format";

function SegmentHistory({ segment }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    setData(null);
    api(`/v1/traffic/segments/${segment.segment_id}/history`, { params: { hours: 72 } })
      .then((r) => setData(r.observations.map((o) => ({ t: new Date(o.observed_at).getTime(), ratio: Math.round(o.speed_ratio * 100), speed: o.current_speed_kmph }))))
      .catch((e) => setError(e.message));
  }, [segment.segment_id]);
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <div className="muted">Loading history…</div>;
  if (data.length < 2) return <div className="muted">Not enough observations yet for a chart ({data.length} so far).</div>;
  return (
    <div className="chart" aria-label={`Speed history for ${segment.name}`}>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
          <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" tickFormatter={(t) => clock(new Date(t).toISOString())} tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 120]} tick={{ fontSize: 11 }} unit="%" width={44} />
          <Tooltip labelFormatter={(t) => clock(new Date(t).toISOString())} formatter={(v, n) => (n === "ratio" ? [`${v}% of free-flow`, "Speed"] : [v, n])} />
          <Line type="monotone" dataKey="ratio" stroke="#2563eb" dot={false} strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="muted small">Collected TomTom observations, last 72 h ({data.length} points).</div>
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

  if (error) return <div className="page"><div className="error-box">{error}</div></div>;
  if (!segments) return <div className="page muted">Loading traffic data…</div>;

  const sorted = [...segments].sort((a, b) => (a.observation?.speed_ratio ?? 9) - (b.observation?.speed_ratio ?? 9));
  const fresh = segments.filter((s) => s.status === "fresh").length;

  return (
    <div className="page">
      <h2>Traffic now</h2>
      <p className="muted">{note}</p>
      <div className="stat-row">
        <div className="stat"><b>{fresh}/{segments.length}</b><span>monitored points fresh</span></div>
        <div className="stat"><b>{incidents?.total_active ?? "–"}</b><span>active incidents · swept {ago(incidents?.last_sweep_at)}</span></div>
        <div className="stat"><b>{models?.routing_forecasts_enabled ? "On" : "Off"}</b><span>Pulse forecasts in routing</span></div>
      </div>
      {models && !models.routing_forecasts_enabled && <div className="note">{models.note}</div>}

      <div className="two-col">
        <section>
          <h3>Monitored points (slowest first)</h3>
          <table className="table">
            <thead>
              <tr><th>Point</th><th>Status</th><th>Speed</th><th>vs free-flow</th><th>Observed</th></tr>
            </thead>
            <tbody>
              {sorted.map((s) => (
                <tr key={s.segment_id} className={selected?.segment_id === s.segment_id ? "sel" : ""} onClick={() => setSelected(s)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSelected(s)}>
                  <td>{s.name}</td>
                  <td>{s.observation ? <span className={`cg-${s.observation.congestion}`}>{s.observation.congestion}</span> : "–"}{s.status !== "fresh" && <span className="muted"> ({s.status.replace("_", " ")})</span>}</td>
                  <td>{s.observation ? `${s.observation.current_speed_kmph} km/h` : "–"}</td>
                  <td>{s.observation ? `${Math.round(s.observation.speed_ratio * 100)}%` : "–"}</td>
                  <td>{s.observation ? ago(s.observation.observed_at) : "never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          {selected ? (
            <>
              <h3>{selected.name}</h3>
              <SegmentHistory segment={selected} />
            </>
          ) : (
            <p className="muted">Select a point to see its collected history.</p>
          )}
          <h3>Weather (Open-Meteo)</h3>
          {weather?.areas?.length ? (
            <ul className="compact">
              {weather.areas.map((a) => (
                <li key={a.area}>
                  {a.area}: {a.temperature_c != null ? `${Math.round(a.temperature_c)}°C` : "–"}
                  {a.precipitation_mm ? `, ${a.precipitation_mm} mm rain` : ""} <span className="muted">({ago(a.observed_at)})</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No weather collected yet.</p>
          )}
          <p className="muted small">{weather?.attribution}</p>
          <h3>Latest incidents</h3>
          <ul className="compact">
            {(incidents?.incidents || []).slice(0, 12).map((i) => (
              <li key={i.id}>
                <b>{i.category.replace(/_/g, " ")}</b> {i.road_from ? `– ${i.road_from}${i.road_to ? ` → ${i.road_to}` : ""}` : ""}{" "}
                <span className="muted">({i.source}{i.delay_s ? `, +${Math.round(i.delay_s / 60)} min` : ""})</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
