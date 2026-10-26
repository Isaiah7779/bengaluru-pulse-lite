import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Icon from "../components/Icons";
import { BASIS_LABEL, clock, km, minutes } from "../format";
import { Journal as JournalNotes } from "./AccountPage";

// Saved journeys: the signed-in user's trip history in PostgreSQL (GET/DELETE /v1/me/trips;
// the server filters by the authenticated account, never by a client-supplied ID).
function SavedJourneys() {
  const [trips, setTrips] = useState(null);
  const [error, setError] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(() => {
    setError(null);
    return api("/v1/me/trips")
      .then(setTrips)
      .catch((e) => {
        setTrips(null);
        setError(e.message);
      });
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function remove(t) {
    if (!window.confirm(`Delete the journey ${t.origin_label || "start"} → ${t.destination_label || "destination"}?`)) return;
    try {
      await api(`/v1/me/trips/${t.id}`, { method: "DELETE" });
      setMsg("Journey deleted.");
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <section className="panel" aria-labelledby="journal-trips">
      <div className="panel-head">
        <h3 id="journal-trips">Saved journeys</h3>
        <a className="link-btn" href="#/navigate">
          Plan a journey
        </a>
      </div>
      {error && (
        <div className="error-box" role="alert">
          Could not load your journeys: {error}{" "}
          <button type="button" className="link-btn" onClick={load}>
            Try again
          </button>
        </div>
      )}
      {!trips && !error && <div className="skeleton" style={{ height: 120 }} aria-label="Loading journeys" />}
      {trips && !trips.length && (
        <div className="empty-state">
          <Icon name="route" size={28} />
          <p>
            <b>No saved journeys yet.</b> When you plan a route, tick <i>Save to my trip history</i> before pressing <i>Find routes</i>, and
            it will appear here.
          </p>
          <a className="button-link primary-link" href="#/navigate">
            Go to Navigate <Icon name="arrow" size={18} />
          </a>
        </div>
      )}
      {trips && trips.length > 0 && (
        <ul className="feed">
          {trips.map((t) => (
            <li key={t.id}>
              <span className="feed-dot" style={{ background: "var(--violet)" }} aria-hidden="true" />
              <div>
                <div className="feed-title">
                  {t.origin_label || "Start"} → {t.destination_label || "Destination"}
                </div>
                <div className="feed-road">
                  {t.vehicle} · {t.preference.replace(/_/g, " ")}
                  {t.chosen_route
                    ? ` · ${minutes(t.chosen_route.eta_s)}, ${km(t.chosen_route.distance_m)} (${BASIS_LABEL[t.chosen_route.eta_basis] || t.chosen_route.eta_basis})`
                    : ""}
                </div>
                <div className="muted small">Saved {clock(t.created_at)}</div>
              </div>
              <div className="feed-meta">
                <button type="button" className="link-btn" onClick={() => remove(t)}>
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {msg && (
        <p className="note" role="status">
          {msg}
        </p>
      )}
    </section>
  );
}

function Notes() {
  const { mode } = useAuth();
  return (
    <section className="panel" aria-labelledby="journal-notes">
      <div className="panel-head">
        <h3 id="journal-notes">Journey notes</h3>
        <span className="eyebrow">Private to you</span>
      </div>
      {mode === "firebase" ? (
        <JournalNotes />
      ) : (
        <div className="empty-state">
          <Icon name="book" size={28} />
          <p>
            <b>Notes are not available on this server yet.</b> Personal notes are kept in a private space tied to your Firebase sign-in, and
            this server still uses its built-in accounts. Your saved journeys above work as normal; notes will appear here once Firebase
            sign-in is switched on.
          </p>
        </div>
      )}
    </section>
  );
}

export default function JournalPage() {
  return (
    <div className="page journal-page">
      <header className="page-head">
        <div>
          <p className="eyebrow">Your journal</p>
          <h2 className="page-title">
            Journeys, <em>remembered.</em>
          </h2>
        </div>
        <p className="page-lede">
          Look back at the trips you saved, how long they were expected to take and on what basis, and keep short notes on what worked and what
          to avoid next time. Only you can see this page's contents.
        </p>
      </header>
      <div className="two-col">
        <SavedJourneys />
        <Notes />
      </div>
    </div>
  );
}
