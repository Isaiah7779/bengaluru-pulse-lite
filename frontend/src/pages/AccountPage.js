import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import PlaceSearch from "../components/PlaceSearch";
import * as personal from "../data/personal";
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

// Firestore-backed favourites (Firebase sign-in).
function Favourites() {
  const [items, setItems] = useState(null);
  const [place, setPlace] = useState(null);
  const [label, setLabel] = useState("");
  const [kind, setKind] = useState("other");
  const [error, setError] = useState(null);
  const load = () =>
    personal
      .listFavorites()
      .then(setItems)
      .catch((e) => {
        setItems([]);
        setError(e.message);
      });
  useEffect(() => {
    load();
  }, []);
  async function add(e) {
    e.preventDefault();
    if (!place) return setError("Search for a place first.");
    setError(null);
    try {
      await personal.addFavorite({ label: label || place.label, detail: place.label, lat: place.lat, lon: place.lon, kind });
      setPlace(null);
      setLabel("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }
  if (!items) return <p className="muted">Loading…</p>;
  return (
    <>
      <p className="muted small">Saved places appear as one-tap choices in the route planner. Stored privately in your Firebase account.</p>
      <ul className="feed">
        {items.map((f) => (
          <li key={f.id}>
            <span className="feed-dot" style={{ background: "var(--violet)" }} aria-hidden="true" />
            <div>
              <div className="feed-title">{f.label}</div>
              <div className="feed-road">
                {f.detail || `${f.lat.toFixed(5)}, ${f.lon.toFixed(5)}`}
                {f.kind && f.kind !== "other" ? ` · ${f.kind}` : ""}
              </div>
            </div>
            <button className="link-btn" onClick={() => personal.removeFavorite(f.id).then(load).catch((e) => setError(e.message))}>
              Remove
            </button>
          </li>
        ))}
        {!items.length && <li className="muted">No favourites yet.</li>}
      </ul>
      <form className="stack-form" onSubmit={add}>
        <PlaceSearch label="Add a place" value={place} onChange={setPlace} onPickOnMap={null} />
        <div className="row2">
          <label>
            Label
            <input placeholder="e.g. Home" maxLength={120} value={label} onChange={(e) => setLabel(e.target.value)} />
          </label>
          <label>
            Type
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="home">Home</option>
              <option value="work">Work</option>
              <option value="other">Other</option>
            </select>
          </label>
        </div>
        <button className="primary">Save place</button>
      </form>
      {error && <div className="error-box">{error}</div>}
    </>
  );
}

const MOODS = [
  ["calm", "Calm"],
  ["okay", "Okay"],
  ["stressful", "Stressful"],
];

export function Journal() {
  const [entries, setEntries] = useState(null);
  const [trips, setTrips] = useState([]);
  const blank = { id: null, title: "", body: "", mood: "", tripId: "" };
  const [form, setForm] = useState(blank);
  const [error, setError] = useState(null);
  const load = () =>
    personal
      .listJournal()
      .then(setEntries)
      .catch((e) => {
        setEntries([]);
        setError(e.message);
      });
  useEffect(() => {
    load();
    api("/v1/me/trips").then(setTrips).catch(() => setTrips([]));
  }, []);
  async function save(e) {
    e.preventDefault();
    setError(null);
    try {
      await personal.saveJournal(form);
      setForm(blank);
      load();
    } catch (err) {
      setError(err.message);
    }
  }
  if (!entries) return <p className="muted">Loading…</p>;
  return (
    <div className="two-col">
      <form className="stack-form" onSubmit={save}>
        <label>
          Title
          <input required maxLength={120} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </label>
        <label>
          Notes
          <textarea rows={5} maxLength={5000} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
        </label>
        <div className="row2">
          <label>
            How was it?
            <select value={form.mood} onChange={(e) => setForm({ ...form, mood: e.target.value })}>
              <option value="">—</option>
              {MOODS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            Saved trip
            <select value={form.tripId} onChange={(e) => setForm({ ...form, tripId: e.target.value })}>
              <option value="">None</option>
              {trips.map((t) => (
                <option key={t.id} value={t.id}>
                  {clock(t.created_at)} · {t.origin_label || "start"} → {t.destination_label || "destination"}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="inline-form">
          <button className="primary">{form.id ? "Update entry" : "Add entry"}</button>
          {form.id && (
            <button type="button" onClick={() => setForm(blank)}>
              Cancel
            </button>
          )}
        </div>
        {error && <div className="error-box">{error}</div>}
      </form>
      <ul className="feed">
        {entries.map((j) => (
          <li key={j.id}>
            <span className="feed-dot" style={{ background: j.mood === "stressful" ? "var(--sev-heavy)" : j.mood === "calm" ? "var(--sev-free)" : "var(--lavender)" }} aria-hidden="true" />
            <div>
              <div className="feed-title">{j.title}</div>
              <div className="feed-road">{j.body}</div>
              <div className="muted small">
                {j.createdAt?.toDate ? clock(j.createdAt.toDate().toISOString()) : "just now"}
                {j.tripId ? ` · trip #${j.tripId}` : ""}
              </div>
            </div>
            <div className="feed-meta">
              <button className="link-btn" onClick={() => setForm({ id: j.id, title: j.title, body: j.body, mood: j.mood || "", tripId: j.tripId || "" })}>
                Edit
              </button>
              <br />
              <button className="link-btn" onClick={() => window.confirm("Delete this journal entry?") && personal.removeJournal(j.id).then(load)}>
                Delete
              </button>
            </div>
          </li>
        ))}
        {!entries.length && <li className="muted">No journal entries yet. Note how a commute went, what to avoid next time.</li>}
      </ul>
    </div>
  );
}

export const VEHICLE_OPTIONS = [
  ["car", "Car"],
  ["motorcycle", "Motorcycle"],
  ["bicycle", "Bicycle"],
  ["walk", "Walk"],
];
export const PREFERENCE_OPTIONS = [
  ["fastest", "Fastest"],
  ["shortest", "Shortest"],
  ["least_traffic_now", "Least traffic now"],
  ["least_traffic_predicted", "Least predicted traffic"],
  ["balanced", "Balanced"],
];

function Preferences() {
  const [prefs, setPrefs] = useState(null);
  const [msg, setMsg] = useState(null);
  useEffect(() => {
    personal
      .getPreferences()
      .then((p) => setPrefs({ vehicle: "car", routePreference: "fastest", avoid: "", departure: "now", ...(p || {}) }))
      .catch((e) => setMsg(e.message));
  }, []);
  if (!prefs) return msg ? <div className="error-box">{msg}</div> : <p className="muted">Loading…</p>;
  async function save(e) {
    e.preventDefault();
    try {
      await personal.savePreferences(prefs);
      setMsg("Saved. The route planner now starts with these choices.");
    } catch (err) {
      setMsg(err.message);
    }
  }
  return (
    <form className="stack-form" onSubmit={save}>
      <label>
        Travel mode
        <select value={prefs.vehicle} onChange={(e) => setPrefs({ ...prefs, vehicle: e.target.value })}>
          {VEHICLE_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        Route preference
        <select value={prefs.routePreference} onChange={(e) => setPrefs({ ...prefs, routePreference: e.target.value })}>
          {PREFERENCE_OPTIONS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </label>
      <label>
        Avoid
        <select value={prefs.avoid} onChange={(e) => setPrefs({ ...prefs, avoid: e.target.value })}>
          <option value="">Nothing</option>
          <option value="toll">Toll roads</option>
          <option value="motorway">Expressways</option>
          <option value="ferry">Ferries</option>
        </select>
      </label>
      <button className="primary">Save preferences</button>
      {msg && <div className="note">{msg}</div>}
    </form>
  );
}

// Built-in-account favourites (PostgreSQL), used only until Firebase sign-in is configured.
function LegacyFavourites() {
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

function FirebaseProfile() {
  const { user, email, firebase, refreshProfile, resetPassword, logout } = useAuth();
  const [name, setName] = useState(user.display_name);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  async function save(e) {
    e.preventDefault();
    try {
      await api("/v1/auth/me", { method: "PATCH", body: { display_name: name } });
      const { auth, A } = await firebase();
      if (auth.currentUser) await A.updateProfile(auth.currentUser, { displayName: name });
      await refreshProfile();
      setMsg("Saved.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function reauthenticate() {
    const { auth, A } = await firebase();
    const u = auth.currentUser;
    const providers = u.providerData.map((p) => p.providerId);
    if (providers.includes("password")) {
      const pw = window.prompt("For your security, enter your password again:");
      if (!pw) throw new Error("Deletion cancelled.");
      await A.reauthenticateWithCredential(u, A.EmailAuthProvider.credential(u.email, pw));
    } else {
      await A.reauthenticateWithPopup(u, new A.GoogleAuthProvider());
    }
  }

  async function remove() {
    const ok = window.confirm(
      "Delete your Bengaluru Pulse account?\n\nThis permanently removes: your saved trips, route submissions and incident reports (server), " +
        "your favourites, journal and preferences (Firestore), and your sign-in. It cannot be undone."
    );
    if (!ok) return;
    setBusy(true);
    setMsg(null);
    try {
      await reauthenticate();
      const { auth } = await firebase();
      const removed = await personal.deleteAllPersonalData();
      await api("/v1/auth/me/delete", { method: "POST", body: { confirm: true } });
      await auth.currentUser.delete();
      setMsg(`Deleted (${removed} personal record(s) in Firestore).`);
      await logout();
    } catch (err) {
      setMsg(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack-form" onSubmit={save}>
      <div className="muted">
        {email || user.email} · role: {user.role} · member since {clock(user.created_at)}
      </div>
      <label>
        Display name
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
      </label>
      <button className="primary">Save</button>
      <button
        type="button"
        onClick={() =>
          resetPassword(email || user.email)
            .then(() => setMsg("Password reset e-mail sent (only for e-mail/password sign-in)."))
            .catch((e) => setMsg(e.message))
        }
      >
        E-mail me a password reset link
      </button>
      {msg && <div className="note">{msg}</div>}
      <button type="button" className="danger" disabled={busy} onClick={remove}>
        {busy ? "Deleting…" : "Delete my account"}
      </button>
    </form>
  );
}

function Profile() {
  const { mode } = useAuth();
  return mode === "firebase" ? <FirebaseProfile /> : <LegacyProfile />;
}

function LegacyProfile() {
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

const FIREBASE_TABS = [
  ["trips", "Trip history", Trips],
  ["favourites", "Favourites", Favourites],
  ["journal", "Journal", Journal],
  ["preferences", "Preferences", Preferences],
  ["contribute", "Share a route", Contribute],
  ["reports", "Report incident", Reports],
  ["profile", "Profile", Profile],
];
const LEGACY_TABS = [
  ["trips", "Trip history", Trips],
  ["favourites", "Favourites", LegacyFavourites],
  ["contribute", "Share a route", Contribute],
  ["reports", "Report incident", Reports],
  ["profile", "Profile", Profile],
];

export default function AccountPage() {
  const { mode } = useAuth();
  const TABS = mode === "firebase" ? FIREBASE_TABS : LEGACY_TABS;
  const [tab, setTab] = useState("trips");
  const Active = (TABS.find((t) => t[0] === tab) || TABS[0])[2];
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Your Bengaluru Pulse</p>
          <h2 className="page-title">
            My <em>account</em>
          </h2>
        </div>
        <p className="page-lede">Trips, places, notes and preferences. Only you can see them.</p>
      </header>
      <div className="tabs" role="tablist">
        {TABS.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="panel tab-panel">
        <Active />
      </div>
    </div>
  );
}
