import { useCallback, useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import Icon from "../components/Icons";
import { CONGESTION_COLORS } from "../config";
import { ago, clock } from "../format";

// Insights are computed in the browser only from what this system has stored and exposes:
//   GET /v1/traffic/segments                 monitored points + latest observation
//   GET /v1/traffic/segments/{id}/history    stored observations per point (hours window)
//   GET /v1/weather/areas                    latest Open-Meteo reading per monitored area
//   GET /v1/incidents?limit=1                active incident count and last sweep
//   GET /v1/forecast/models                  registered models and whether any is used
// Nothing is estimated or filled in: missing data is shown as missing.
const HISTORY_HOURS = 72;
const BUCKET_MIN = 30;
const LEVELS = ["FREE", "MODERATE", "HEAVY", "SEVERE", "CLOSED"];

function useLoad(loader) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const run = useCallback(() => {
    setState({ data: null, error: null, loading: true });
    loader()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((e) => setState({ data: null, error: e.message, loading: false }));
  }, [loader]);
  useEffect(() => {
    run();
  }, [run]);
  return [state, run];
}

async function inBatches(items, size, fn) {
  const out = [];
  for (let i = 0; i < items.length; i += size) out.push(...(await Promise.all(items.slice(i, i + size).map(fn))));
  return out;
}

const loadSegments = () => api("/v1/traffic/segments");
const loadWeather = () => api("/v1/weather/areas");
const loadModels = () => api("/v1/forecast/models");
const loadIncidents = () => api("/v1/incidents", { params: { limit: 1 } });

function Failed({ what, error, retry }) {
  return (
    <div className="error-box" role="alert">
      {what} could not be loaded: {error}{" "}
      <button type="button" className="link-btn" onClick={retry}>
        Try again
      </button>
    </div>
  );
}

function Empty({ children }) {
  return (
    <div className="empty-state">
      <Icon name="info" size={24} />
      <p>{children}</p>
    </div>
  );
}

function coverage(segments) {
  const pts = segments.filter((s) => s.lat != null && s.lon != null);
  if (pts.length < 2) return null;
  const lats = pts.map((s) => s.lat);
  const lons = pts.map((s) => s.lon);
  const midLat = ((Math.min(...lats) + Math.max(...lats)) / 2) * (Math.PI / 180);
  return {
    ns: (Math.max(...lats) - Math.min(...lats)) * 111.2,
    ew: (Math.max(...lons) - Math.min(...lons)) * 111.2 * Math.cos(midLat),
  };
}

function Overview({ seg, inc, retrySeg }) {
  if (seg.loading) return <div className="skeleton" style={{ height: 150 }} aria-label="Loading overview" />;
  if (seg.error) return <Failed what="Traffic overview" error={seg.error} retry={retrySeg} />;
  const segments = seg.data.segments;
  if (!segments.length) return <Empty>No monitored points are configured yet.</Empty>;
  const fresh = segments.filter((s) => s.status === "fresh");
  const latest = segments.map((s) => s.observation?.observed_at).filter(Boolean).sort().pop();
  const counts = Object.fromEntries(LEVELS.map((l) => [l, fresh.filter((s) => s.observation?.congestion === l).length]));
  const box = coverage(segments);
  const allStale = !fresh.length;
  return (
    <>
      {allStale && (
        <div className="warning" role="status">
          No reading is fresher than {seg.data.stale_after_minutes} minutes. The figures below are the last stored values, not current
          conditions.
        </div>
      )}
      <div className="stat-row">
        <div className="stat">
          <p className="eyebrow">Monitored points</p>
          <b>
            {fresh.length}
            <small>/{segments.length}</small>
          </b>
          <span>fresh · latest reading {latest ? ago(latest) : "none yet"}</span>
        </div>
        <div className="stat">
          <p className="eyebrow">Area spanned</p>
          <b>{box ? `${Math.round(box.ns)}×${Math.round(box.ew)}` : "–"}</b>
          <span>km north–south × east–west between the outermost points</span>
        </div>
        <div className="stat">
          <p className="eyebrow">Heavy or worse now</p>
          <b>{counts.HEAVY + counts.SEVERE + counts.CLOSED}</b>
          <span>of the fresh points</span>
        </div>
        <div className="stat">
          <p className="eyebrow">Active incidents</p>
          <b>{inc.data ? inc.data.total_active : "–"}</b>
          <span>{inc.data ? `TomTom, swept ${ago(inc.data.last_sweep_at)}` : inc.error ? "unavailable" : "loading…"}</span>
        </div>
      </div>
      {fresh.length > 0 && (
        <div className="sev-bar" role="img" aria-label={LEVELS.map((l) => `${counts[l]} ${l.toLowerCase()}`).join(", ")}>
          {LEVELS.filter((l) => counts[l]).map((l) => (
            <span key={l} style={{ flex: counts[l], background: CONGESTION_COLORS[l] }} title={`${counts[l]} ${l.toLowerCase()}`} />
          ))}
        </div>
      )}
      <p className="muted small">{seg.data.coverage_note}</p>
    </>
  );
}

function useHistories(seg) {
  const [state, setState] = useState({ rows: null, failed: 0, loading: true });
  const load = useCallback(() => {
    if (!seg.data) return;
    setState({ rows: null, failed: 0, loading: true });
    inBatches(seg.data.segments, 6, (s) =>
      api(`/v1/traffic/segments/${s.segment_id}/history`, { params: { hours: HISTORY_HOURS } })
        .then((r) => ({ s, obs: r.observations }))
        .catch(() => ({ s, obs: null }))
    ).then((rows) => setState({ rows, failed: rows.filter((r) => !r.obs).length, loading: false }));
  }, [seg.data]);
  useEffect(() => {
    load();
  }, [load]);
  return [state, load];
}

function Trends({ hist, seg, retry }) {
  const series = useMemo(() => {
    if (!hist.rows) return null;
    const buckets = new Map();
    for (const { obs } of hist.rows) {
      for (const o of obs || []) {
        if (o.speed_ratio == null) continue;
        const t = Math.floor(new Date(o.observed_at).getTime() / (BUCKET_MIN * 60000)) * BUCKET_MIN * 60000;
        const b = buckets.get(t) || { t, sum: 0, n: 0 };
        b.sum += o.speed_ratio;
        b.n += 1;
        buckets.set(t, b);
      }
    }
    return [...buckets.values()].sort((a, b) => a.t - b.t).map((b) => ({ t: b.t, ratio: Math.round((b.sum / b.n) * 100), n: b.n }));
  }, [hist.rows]);

  if (seg.error) return <Empty>Trends need the monitored-point list, which failed to load above.</Empty>;
  if (hist.loading) return <div className="skeleton" style={{ height: 240 }} aria-label="Loading trends" />;
  if (!series || series.length < 2) return <Empty>Not enough stored observations yet to draw a trend. Readings are collected every 30 minutes.</Empty>;
  const spanH = (series[series.length - 1].t - series[0].t) / 3600000;
  const total = series.reduce((a, b) => a + b.n, 0);
  return (
    <>
      <div className="chart" aria-label="Average speed as a share of free-flow across monitored points">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={series} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="t" type="number" scale="time" domain={["dataMin", "dataMax"]} tickFormatter={(t) => clock(new Date(t).toISOString())} tick={{ fontSize: 11 }} stroke="var(--grid)" />
            <YAxis domain={[0, 110]} unit="%" width={44} tick={{ fontSize: 11 }} stroke="var(--grid)" />
            <ReferenceLine y={100} stroke="var(--warm-gray)" strokeDasharray="4 4" />
            <Tooltip
              labelFormatter={(t) => clock(new Date(t).toISOString())}
              formatter={(v, n, p) => [`${v}% of free-flow (${p.payload.n} readings)`, "Average"]}
              contentStyle={{ background: "#171419", border: "none", borderRadius: 10, color: "#FBF7F1", fontSize: 12 }}
              itemStyle={{ color: "#FBF7F1" }}
            />
            <Line type="monotone" dataKey="ratio" stroke="#5925B5" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        Average of {total} stored readings in {BUCKET_MIN}-minute steps, {clock(new Date(series[0].t).toISOString())} –{" "}
        {clock(new Date(series[series.length - 1].t).toISOString())} ({spanH < 48 ? `${Math.round(spanH)} hours` : `${Math.round(spanH / 24)} days`}, last{" "}
        {HISTORY_HOURS} h window). 100% = free-flow speed.
        {spanH < 24 && " Less than a day has been collected so far, so this is not yet a daily pattern."}
        {hist.failed > 0 && ` History for ${hist.failed} point(s) could not be loaded and is left out.`}
      </p>
      {hist.failed > 0 && (
        <button type="button" className="link-btn" onClick={retry}>
          Retry missing points
        </button>
      )}
    </>
  );
}

function Comparison({ hist }) {
  const rows = useMemo(() => {
    if (!hist.rows) return null;
    return hist.rows
      .map(({ s, obs }) => {
        const vals = (obs || []).map((o) => o.speed_ratio).filter((v) => v != null);
        if (!vals.length) return null;
        const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
        return { name: s.name, mean: Math.round(mean * 100), min: Math.round(Math.min(...vals) * 100), n: vals.length };
      })
      .filter(Boolean)
      .sort((a, b) => a.mean - b.mean);
  }, [hist.rows]);
  if (hist.loading) return <div className="skeleton" style={{ height: 320 }} aria-label="Loading comparison" />;
  if (!rows || !rows.length) return <Empty>No stored readings to compare yet.</Empty>;
  const slowest = rows.slice(0, 10);
  const colour = (v) => (v >= 85 ? CONGESTION_COLORS.FREE : v >= 65 ? CONGESTION_COLORS.MODERATE : v >= 45 ? CONGESTION_COLORS.HEAVY : CONGESTION_COLORS.SEVERE);
  return (
    <>
      <div className="chart" aria-label="Monitored points with the lowest average speed">
        <ResponsiveContainer width="100%" height={Math.max(220, slowest.length * 30)}>
          <BarChart data={slowest} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--grid)" horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11 }} stroke="var(--grid)" />
            <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11 }} stroke="var(--grid)" />
            <Tooltip
              formatter={(v, n, p) => [`${v}% average · lowest ${p.payload.min}% · ${p.payload.n} readings`, "Speed vs free-flow"]}
              contentStyle={{ background: "#171419", border: "none", borderRadius: 10, color: "#FBF7F1", fontSize: 12 }}
              itemStyle={{ color: "#FBF7F1" }}
            />
            <Bar dataKey="mean" radius={[0, 6, 6, 0]} isAnimationActive={false}>
              {slowest.map((r) => (
                <Cell key={r.name} fill={colour(r.mean)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        The {slowest.length} slowest of {rows.length} points with stored readings, by average speed as a share of free-flow over the same window.
        Full live list: <a href="#/traffic">Traffic</a>.
      </p>
    </>
  );
}

function WeatherContext({ wx, retry }) {
  if (wx.loading) return <div className="skeleton" style={{ height: 110 }} aria-label="Loading weather" />;
  if (wx.error) return <Failed what="Weather" error={wx.error} retry={retry} />;
  const areas = wx.data.areas || [];
  if (!areas.length) return <Empty>No weather has been collected yet.</Empty>;
  const wet = areas.filter((a) => a.precipitation_mm > 0);
  const temps = areas.map((a) => a.temperature_c).filter((t) => t != null);
  return (
    <>
      <p>
        {temps.length ? `${Math.round(Math.min(...temps))}–${Math.round(Math.max(...temps))}°C across ${areas.length} monitored areas` : "Temperatures unavailable"}
        {wet.length ? `; rain reported in ${wet.map((a) => a.area).join(", ")}.` : "; no rain in the latest readings."}
      </p>
      <div className="weather-grid">
        {areas.map((a) => (
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
      <p className="muted small">
        Latest reading per area. {wx.data.attribution}. Weather history is stored but not yet exposed by the API, so it is not charted here.
      </p>
    </>
  );
}

function DataKinds({ models, retry }) {
  const active = models.data?.routing_forecasts_enabled;
  const counts = (models.data?.models || []).reduce((acc, m) => ({ ...acc, [m.status]: (acc[m.status] || 0) + 1 }), {});
  return (
    <div className="kinds">
      <article className="kind">
        <p className="eyebrow">Observed</p>
        <h4>Measured readings</h4>
        <p>
          Speeds read from TomTom Traffic Flow at the monitored points every 30 minutes and stored with their time. Everything charted on this
          page is observed data.
        </p>
      </article>
      <article className="kind">
        <p className="eyebrow">Provider estimate</p>
        <h4>Routing travel times</h4>
        <p>
          Route times on Navigate come from TomTom's routing service: live traffic for "leave now", TomTom's own prediction for later departures,
          and its "typical" historic time. They are TomTom's estimates, not ours.
        </p>
      </article>
      <article className="kind kind--dark">
        <p className="eyebrow">Forecast</p>
        <h4>Bengaluru Pulse models</h4>
        {models.loading && <p>Loading model status…</p>}
        {models.error && <Failed what="Model status" error={models.error} retry={retry} />}
        {models.data && (
          <p>
            {active
              ? "A model that passed evaluation is used for routing."
              : `Not used yet. ${models.data.note}`}{" "}
            Registered: {Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(", ") || "none"}.
          </p>
        )}
      </article>
    </div>
  );
}

export default function InsightsPage() {
  const [seg, retrySeg] = useLoad(loadSegments);
  const [wx, retryWx] = useLoad(loadWeather);
  const [models, retryModels] = useLoad(loadModels);
  const [inc] = useLoad(loadIncidents);
  const [hist, retryHist] = useHistories(seg);

  return (
    <div className="page insights-page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Insights</p>
          <h2 className="page-title">
            What the data <em>shows.</em>
          </h2>
        </div>
        <p className="page-lede">
          Patterns from the traffic and weather readings Bengaluru Pulse has actually stored, with the coverage and age of every figure. For the
          live point-by-point view, see <a href="#/traffic">Traffic</a>.
        </p>
      </header>

      <section className="panel" aria-labelledby="ins-overview">
        <div className="panel-head">
          <h3 id="ins-overview">Traffic overview</h3>
          <span className="eyebrow">Latest readings</span>
        </div>
        <Overview seg={seg} inc={inc} retrySeg={retrySeg} />
      </section>

      <div className="two-col">
        <section className="panel" aria-labelledby="ins-trend">
          <div className="panel-head">
            <h3 id="ins-trend">City trend</h3>
            <span className="eyebrow">Stored observations</span>
          </div>
          <Trends hist={hist} seg={seg} retry={retryHist} />
        </section>
        <section className="panel" aria-labelledby="ins-compare">
          <div className="panel-head">
            <h3 id="ins-compare">Slowest monitored points</h3>
            <span className="eyebrow">Same window</span>
          </div>
          <Comparison hist={hist} />
        </section>
      </div>

      <section className="panel" aria-labelledby="ins-weather">
        <div className="panel-head">
          <h3 id="ins-weather">Weather context</h3>
          <span className="eyebrow">Open-Meteo</span>
        </div>
        <WeatherContext wx={wx} retry={retryWx} />
      </section>

      <section className="panel" aria-labelledby="ins-kinds">
        <div className="panel-head">
          <h3 id="ins-kinds">Observed, estimated or forecast?</h3>
          <span className="eyebrow">Reading the numbers</span>
        </div>
        <DataKinds models={models} retry={retryModels} />
      </section>
    </div>
  );
}
