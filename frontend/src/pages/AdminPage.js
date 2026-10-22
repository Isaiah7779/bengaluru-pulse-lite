import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { ago, clock, km, minutes } from "../format";

function useLoad(path) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const reload = useCallback(() => {
    setError(null);
    return api(path).then(setData).catch((e) => setError(e.message));
  }, [path]);
  useEffect(() => {
    reload();
  }, [reload]);
  return [data, error, reload];
}

function Users() {
  const { user: me } = useAuth();
  const [data, error, reload] = useLoad("/v1/admin/users");
  const [msg, setMsg] = useState(null);
  async function patch(id, body) {
    setMsg(null);
    try {
      await api(`/v1/admin/users/${id}`, { method: "PATCH", body });
      reload();
    } catch (err) {
      setMsg(err.message);
    }
  }
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <>
      {msg && <div className="error-box">{msg}</div>}
      <p className="muted">{data.total} account(s). Administrators cannot change their own role or status; the last active administrator is protected.</p>
      <table className="table">
        <thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Actions</th></tr></thead>
        <tbody>
          {data.users.map((u) => (
            <tr key={u.id}>
              <td>{u.display_name}<div className="muted small">{u.email}</div></td>
              <td>{u.role}</td>
              <td>{u.is_active ? "active" : "disabled"}</td>
              <td>{u.last_login_at ? ago(u.last_login_at) : "never"}</td>
              <td>
                {u.id === me.id ? (
                  <span className="muted">you</span>
                ) : (
                  <>
                    <button className="link-btn" onClick={() => patch(u.id, { role: u.role === "admin" ? "user" : "admin" })}>
                      {u.role === "admin" ? "Make user" : "Make admin"}
                    </button>{" "}
                    <button className="link-btn" onClick={() => patch(u.id, { is_active: !u.is_active })}>
                      {u.is_active ? "Disable" : "Enable"}
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Moderation() {
  const [state, setState] = useState("under_review");
  const [cands, error, reload] = useLoad(`/v1/admin/community/candidates?state=${state}`);
  const [pending, , reloadPending] = useLoad("/v1/admin/incidents/pending");
  const [msg, setMsg] = useState(null);

  async function decide(id, decision) {
    const note = window.prompt(`Note for ${decision} (optional):`) ?? null;
    try {
      await api(`/v1/admin/community/candidates/${id}/decision`, { method: "POST", body: { decision, note } });
      reload();
    } catch (err) {
      setMsg(err.message);
    }
  }
  async function moderate(id, decision) {
    await api(`/v1/admin/incidents/${id}/decision`, { method: "POST", body: { decision } }).catch((e) => setMsg(e.message));
    reloadPending();
  }
  return (
    <>
      {msg && <div className="error-box">{msg}</div>}
      <h3>Shortcut candidates</h3>
      <div className="tabs small">
        {["under_review", "candidate", "verified", "rejected", "stale"].map((s) => (
          <button key={s} className={state === s ? "on" : ""} onClick={() => setState(s)}>{s.replace("_", " ")}</button>
        ))}
      </div>
      {error && <div className="error-box">{error}</div>}
      <table className="table">
        <thead><tr><th>#</th><th>Type</th><th>Mode</th><th>Route vs reference</th><th>Confirmations</th><th>Checks</th><th>Decision</th></tr></thead>
        <tbody>
          {(cands?.candidates || []).map((c) => (
            <tr key={c.id}>
              <td>{c.id}</td>
              <td>{c.classification}</td>
              <td>{c.vehicle}</td>
              <td>
                {km(c.distance_m)} vs {km(c.reference_distance_m)}
                <div className="muted small">median observed {minutes(c.median_observed_duration_s)}</div>
              </td>
              <td>{c.confirmations}/{c.required_confirmations}</td>
              <td className="small">{c.checks ? `agreement ${c.checks.classification_agreement}, ${c.checks.consistent ? "consistent" : "inconsistent"}` : "–"}</td>
              <td>
                {c.state === "under_review" && <button className="link-btn" onClick={() => decide(c.id, "verify")}>Verify</button>}{" "}
                {c.state !== "rejected" && <button className="link-btn" onClick={() => decide(c.id, "reject")}>Reject</button>}{" "}
                {c.state === "verified" && <button className="link-btn" onClick={() => decide(c.id, "stale")}>Mark stale</button>}
              </td>
            </tr>
          ))}
          {cands && !cands.candidates.length && <tr><td colSpan={7} className="muted">None in this state.</td></tr>}
        </tbody>
      </table>
      <h3>Community incident reports awaiting review</h3>
      <ul className="compact">
        {(pending?.incidents || []).map((i) => (
          <li key={i.id}>
            <b>{i.category.replace(/_/g, " ")}</b>: {i.description} <span className="muted">({i.lat.toFixed(4)}, {i.lon.toFixed(4)})</span>{" "}
            <button className="link-btn" onClick={() => moderate(i.id, "publish")}>Publish</button>{" "}
            <button className="link-btn" onClick={() => moderate(i.id, "reject")}>Reject</button>
          </li>
        ))}
        {pending && !pending.incidents.length && <li className="muted">No pending reports.</li>}
      </ul>
    </>
  );
}

function Freshness() {
  const [data, error] = useLoad("/v1/admin/data-freshness");
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  const t = data.traffic;
  return (
    <>
      <div className="stat-row">
        <div className="stat"><b>{t.segments_fresh}/{t.segments_total}</b><span>points fresh (≤ {data.stale_after_minutes} min)</span></div>
        <div className="stat"><b>{t.observations_total}</b><span>flow observations since {t.first_observation_at ? clock(t.first_observation_at) : "–"}</span></div>
        <div className="stat"><b>{data.weather.observations_total}</b><span>weather observations, last {ago(data.weather.last_observation_at)}</span></div>
        <div className="stat"><b>{data.incidents.active}</b><span>active incidents, last sweep {ago(data.incidents.last_seen_at)}</span></div>
      </div>
      <h4>Provider calls today (UTC)</h4>
      <table className="table">
        <thead><tr><th>Provider</th><th>Purpose</th><th>OK</th><th>Calls</th></tr></thead>
        <tbody>
          {data.provider_calls_today.map((c, i) => (
            <tr key={i}><td>{c.provider}</td><td>{c.purpose}</td><td>{c.ok ? "yes" : "no"}</td><td>{c.count}</td></tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Models() {
  const [data, error] = useLoad("/v1/admin/models");
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.models.length) return <p className="muted">No models registered. Run <code>python -m forecasting.pipeline research|segments</code>.</p>;
  return data.models.map((m) => {
    const tests = m.evaluations.filter((e) => e.split === "test" && e.metric === "mae");
    return (
      <div key={m.id} className="model-card">
        <h4>{m.name} <span className="muted">v{m.version}</span> <span className={`badge badge-${m.status}`}>{m.status}</span></h4>
        <div className="small muted">{m.task} · {m.dataset}</div>
        <div className="small">{m.algorithm}</div>
        <table className="table small">
          <thead><tr><th>Horizon</th><th>Candidate</th><th>Test MAE</th><th>n</th></tr></thead>
          <tbody>
            {tests.map((e, i) => (
              <tr key={i}><td>{e.horizon}</td><td>{e.candidate}</td><td>{e.value.toFixed(4)}</td><td>{e.n}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  });
}

function SystemHealth() {
  const [data, error, reload] = useLoad("/v1/admin/system-health");
  if (error) return <div className="error-box">{error}</div>;
  if (!data) return <p className="muted">Checking…</p>;
  return (
    <>
      <button className="link-btn" onClick={reload}>Re-check</button>
      <table className="table">
        <thead><tr><th>Component</th><th>Status</th><th>Detail</th></tr></thead>
        <tbody>
          {Object.entries(data.checks).map(([k, v]) => (
            <tr key={k}>
              <td>{k.replace(/_/g, " ")}</td>
              <td className={`st-${v.status}`}>{v.status.replace(/_/g, " ")}</td>
              <td className="small">{Object.entries(v).filter(([kk]) => kk !== "status").map(([kk, vv]) => `${kk}: ${vv}`).join(" · ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small muted">
        {Object.entries(data.counts).map(([k, v]) => `${k}: ${v}`).join(" · ")} · {data.environment} · v{data.version}
      </p>
    </>
  );
}

function Audit() {
  const [data, error] = useLoad("/v1/admin/audit-log");
  if (error) return <div className="error-box">{error}</div>;
  return (
    <ul className="compact">
      {(data?.entries || []).map((e) => (
        <li key={e.id}>
          {clock(e.created_at)} · <b>{e.action}</b> {e.target} <span className="muted">by {e.actor_user_id ?? "system"}</span>
        </li>
      ))}
    </ul>
  );
}

const TABS = [
  ["health", "System health", SystemHealth],
  ["freshness", "Data freshness", Freshness],
  ["moderation", "Moderation", Moderation],
  ["models", "Models & metrics", Models],
  ["users", "Users", Users],
  ["audit", "Audit log", Audit],
];

export default function AdminPage() {
  const [tab, setTab] = useState("health");
  const Active = TABS.find((t) => t[0] === tab)[2];
  return (
    <div className="page">
      <h2>Administration</h2>
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
