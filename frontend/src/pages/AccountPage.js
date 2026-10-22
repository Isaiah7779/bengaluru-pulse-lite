import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BASIS_LABEL, CLASS_LABEL, ago, clock, km, minutes } from "../format";

export function parseGpx(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const pts = [...doc.getElementsByTagName("trkpt"), ...doc.getElementsByTagName("rtept")];
  return pts
    .map((p) => ({
      lat: parseFloat(p.getAttribute("lat")),
      lon: parseFloat(p.getAttribute("lon")),
      t: p.getElementsByTagName("time")[0]?.textContent,
    }))
    .filter((p) => !Number.isNaN(p.lat) && !Number.isNaN(p.lon) && p.t);
}

function Trips() {
  const [trips, setTrips] = useState(null);
  const load = () => api("/v1/me/trips").then(setTrips).catch(() => setTrips([]));
  useEffect(() => {
    load();
  }, []);
  if (!trips) return <p className="muted">Loading…</p>;
  if (!trips.length) return <p className="muted">No saved trips. Tick “Save to my trip history” when planning a route.</p>;
  return (
    <>
      <table className="table">
        <thead>
          <tr><th>When</th><th>From → To</th><th>Mode</th><th>Chosen route</th><th /></tr>
        </thead>
        <tbody>
          {trips.map((t) => (
            <tr key={t.id}>
              <td>{clock(t.created_at)}</td>
              <td>{t.origin_label || "start"} → {t.destination_label || "destination"}</td>
              <td>{t.vehicle} · {t.preference.replace(/_/g, " ")}</td>
              <td>
                {t.chosen_route ? `${minutes(t.chosen_route.eta_s)}, ${km(t.chosen_route.distance_m)} (${BASIS_LABEL[t.chosen_route.eta_basis] || t.chosen_route.eta_basis})` : "–"}
              </td>
              <td>
                <button className="link-btn" onClick={() => api(`/v1/me/trips/${t.id}`, { method: "DELETE" }).then(load)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="link-btn" onClick={() => window.confirm("Delete all saved trips?") && api("/v1/me/trips", { method: "DELETE" }).then(load)}>
        Delete all trips
      </button>
    </>
  );
}

function Favourites() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ label: "", lat: "", lon: "" });
  const [error, setError] = useState(null);
  const load = () => api("/v1/me/favourites").then(setItems).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);
  async function add(e) {
    e.preventDefault();
    setError(null);
    try {
      await api("/v1/me/favourites", { method: "POST", body: { label: form.label, lat: Number(form.lat), lon: Number(form.lon) } });
      setForm({ label: "", lat: "", lon: "" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <>
      <ul className="compact">
        {items.map((f) => (
          <li key={f.id}>
            <b>{f.label}</b> {f.lat.toFixed(5)}, {f.lon.toFixed(5)}{" "}
            <button className="link-btn" onClick={() => api(`/v1/me/favourites/${f.id}`, { method: "DELETE" }).then(load)}>Remove</button>
          </li>
        ))}
        {!items.length && <li className="muted">No favourites yet.</li>}
      </ul>
      <form className="inline-form" onSubmit={add}>
        <input required placeholder="Label (e.g. Home)" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
        <input required placeholder="Latitude" inputMode="decimal" value={form.lat} onChange={(e) => setForm({ ...form, lat: e.target.value })} />
        <input required placeholder="Longitude" inputMode="decimal" value={form.lon} onChange={(e) => setForm({ ...form, lon: e.target.value })} />
        <button className="primary">Add</button>
      </form>
      {error && <div className="error-box">{error}</div>}
    </>
  );
}

function Contribute() {
  const [vehicle, setVehicle] = useState("car");
  const [points, setPoints] = useState([]);
  const [recording, setRecording] = useState(false);
  const [note, setNote] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [mine, setMine] = useState([]);
  const watch = useRef(null);

  const loadMine = () => api("/v1/community/submissions/mine").then((r) => setMine(r.submissions)).catch(() => {});
  useEffect(() => {
    loadMine();
    return () => watch.current != null && navigator.geolocation?.clearWatch(watch.current);
  }, []);

  function toggleRecording() {
    if (recording) {
      navigator.geolocation.clearWatch(watch.current);
      watch.current = null;
      setRecording(false);
      return;
    }
    if (!navigator.geolocation) {
      setError("GPS is not available in this browser.");
      return;
    }
    setPoints([]);
    setResult(null);
    watch.current = navigator.geolocation.watchPosition(
      (pos) =>
        setPoints((p) => [
          ...p,
          { lat: pos.coords.latitude, lon: pos.coords.longitude, t: new Date(pos.timestamp).toISOString(), accuracy_m: pos.coords.accuracy },
        ]),
      (err) => setError(err.message),
      { enableHighAccuracy: true, maximumAge: 0 }
    );
    setRecording(true);
  }

  async function onFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    try {
      const pts = file.name.toLowerCase().endsWith(".json") ? JSON.parse(text) : parseGpx(text);
      setPoints(pts);
      setError(pts.length ? null : "No timestamped track points found in that file.");
    } catch {
      setError("Could not read that file (expected GPX or JSON).");
    }
  }

  async function submit() {
    setError(null);
    try {
      const res = await api("/v1/community/submissions", { method: "POST", body: { vehicle, points, note: note || null } });
      setResult(res);
      loadMine();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <p className="muted">
        Share a trip you actually made. It is map-matched on legal roads for your vehicle and compared with the standard route. A shortcut
        needs at least three independent drivers and an administrator's review before it is shown to anyone.
      </p>
      <div className="inline-form">
        <select value={vehicle} onChange={(e) => setVehicle(e.target.value)} aria-label="Vehicle">
          <option value="car">Car</option>
          <option value="motorcycle">Motorcycle</option>
          <option value="bicycle">Bicycle</option>
          <option value="walk">Walk</option>
        </select>
        <button type="button" className={recording ? "danger" : "primary"} onClick={toggleRecording}>
          {recording ? "Stop recording" : "Record a trip with GPS"}
        </button>
        <label className="file-btn">
          Upload GPX/JSON
          <input type="file" accept=".gpx,.json,application/gpx+xml,application/json" onChange={onFile} hidden />
        </label>
      </div>
      <p className="small">{points.length} point(s) captured{recording ? " — recording…" : ""}.</p>
      <input className="wide" placeholder="Optional note (e.g. avoids the Silk Board signal)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
      <button className="primary" disabled={recording || points.length < 10} onClick={submit}>Submit trip</button>
      {error && <div className="error-box">{error}</div>}
      {result && (
        <div className={`result-box ${result.status}`}>
          <b>Submission {result.status}.</b> {result.rejection_reason || result.checks?.note || ""}
          {result.candidate && (
            <div>
              Linked to a {CLASS_LABEL[result.candidate.classification]?.toLowerCase()} candidate: {result.candidate.confirmations}/
              {result.candidate.required_confirmations} independent confirmations ({result.candidate.state.replace("_", " ")}).
            </div>
          )}
        </div>
      )}
      <h4>My submissions</h4>
      <ul className="compact">
        {mine.map((s) => (
          <li key={s.id}>
            {clock(s.submitted_at)} · {s.vehicle} · <b>{s.status}</b>
            {s.rejection_reason ? ` — ${s.rejection_reason}` : ""}
            {s.matched_distance_m ? ` · ${km(s.matched_distance_m)} in ${minutes(s.observed_duration_s)}` : ""}
          </li>
        ))}
        {!mine.length && <li className="muted">None yet.</li>}
      </ul>
    </>
  );
}

function Reports() {
  const [form, setForm] = useState({ category: "flooding", description: "", lat: "", lon: "" });
  const [mine, setMine] = useState([]);
  const [msg, setMsg] = useState(null);
  const load = () => api("/v1/incidents/mine").then((r) => setMine(r.reports)).catch(() => {});
  useEffect(() => {
    load();
  }, []);
  function here() {
    navigator.geolocation?.getCurrentPosition((p) => setForm((f) => ({ ...f, lat: p.coords.latitude.toFixed(6), lon: p.coords.longitude.toFixed(6) })));
  }
  async function submit(e) {
    e.preventDefault();
    try {
      const r = await api("/v1/incidents/report", { method: "POST", body: { ...form, lat: Number(form.lat), lon: Number(form.lon) } });
      setMsg(r.message);
      setForm({ ...form, description: "" });
      load();
    } catch (err) {
      setMsg(err.message);
    }
  }
  return (
    <>
      <form className="stack-form" onSubmit={submit}>
        <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} aria-label="Incident type">
          {["flooding", "accident", "road_closed", "road_works", "jam", "broken_down_vehicle", "dangerous_conditions", "other"].map((c) => (
            <option key={c} value={c}>{c.replace(/_/g, " ")}</option>
          ))}
        </select>
        <textarea required minLength={5} maxLength={500} placeholder="What is happening?" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <div className="inline-form">
          <input required placeholder="Latitude" value={form.lat} onChange={(e) => setForm({ ...form, lat: e.target.value })} />
          <input required placeholder="Longitude" value={form.lon} onChange={(e) => setForm({ ...form, lon: e.target.value })} />
          <button type="button" onClick={here}>Use my location</button>
        </div>
        <button className="primary">Report incident</button>
      </form>
      {msg && <div className="note">{msg}</div>}
      <h4>My reports</h4>
      <ul className="compact">
        {mine.map((r) => (
          <li key={r.id}>{r.category.replace(/_/g, " ")} — {r.status} <span className="muted">({ago(r.last_seen_at)})</span></li>
        ))}
        {!mine.length && <li className="muted">None yet.</li>}
      </ul>
    </>
  );
}

function Profile() {
  const { user, logout } = useAuth();
  const [name, setName] = useState(user.display_name);
  const [pw, setPw] = useState({ current: "", next: "" });
  const [msg, setMsg] = useState(null);
  async function save(e) {
    e.preventDefault();
    try {
      const body = { display_name: name };
      if (pw.next) Object.assign(body, { current_password: pw.current, new_password: pw.next });
      await api("/v1/auth/me", { method: "PATCH", body });
      setMsg("Saved.");
      setPw({ current: "", next: "" });
    } catch (err) {
      setMsg(err.message);
    }
  }
  async function remove() {
    const password = window.prompt("Deleting your account removes your trips, favourites and submissions. Enter your password to confirm:");
    if (!password) return;
    try {
      await api("/v1/auth/me/delete", { method: "POST", body: { password } });
      await logout();
    } catch (err) {
      setMsg(err.message);
    }
  }
  return (
    <form className="stack-form" onSubmit={save}>
      <div className="muted">{user.email} · role: {user.role} · member since {clock(user.created_at)}</div>
      <label>Display name<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></label>
      <label>Current password<input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></label>
      <label>New password<input type="password" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></label>
      <button className="primary">Save</button>
      {msg && <div className="note">{msg}</div>}
      <button type="button" className="danger" onClick={remove}>Delete my account</button>
    </form>
  );
}

const TABS = [
  ["trips", "Trip history", Trips],
  ["favourites", "Favourites", Favourites],
  ["contribute", "Share a route", Contribute],
  ["reports", "Report incident", Reports],
  ["profile", "Profile", Profile],
];

export default function AccountPage() {
  const [tab, setTab] = useState("trips");
  const Active = TABS.find((t) => t[0] === tab)[2];
  return (
    <div className="page">
      <h2>My account</h2>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        <Active />
      </div>
    </div>
  );
}
