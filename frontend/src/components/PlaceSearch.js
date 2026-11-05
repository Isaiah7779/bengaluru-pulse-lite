import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api/client";

export const MIN_CHARS = 3; // matches the backend's GEOCODE_MIN_CHARS
const DEBOUNCE_MS = 350;

/** What to tell the user when a search request fails (never "no matching place"). */
export function searchErrorMessage(err) {
  if (err && err.code === "network_error") return "Can't reach the server. Check your connection and try again.";
  if (err && (err.code === "geocoder_rate_limited" || err.status === 429))
    return "Place search is busy right now. Wait a few seconds and try again, or pick the place on the map.";
  if (err && (err.code === "geocoder_unavailable" || err.status >= 500))
    return "Place search is temporarily unavailable. Try again shortly or pick the place on the map.";
  if (err && err.status === 401) return "Your session has ended. Sign in again to search places.";
  return (err && err.message) || "Place search failed. Try again or pick the place on the map.";
}

/** Search box with suggestions, current-location and pick-on-map actions. */
export default function PlaceSearch({ label, value, onChange, onPickOnMap, picking, near }) {
  const [text, setText] = useState(value?.label || "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [searched, setSearched] = useState(false); // last query got a real (possibly empty) answer
  const typed = useRef(false);
  const listId = useId();

  useEffect(() => {
    if (!typed.current) setText(value?.label || "");
  }, [value]);

  useEffect(() => {
    if (!typed.current) return undefined;
    const q = text.trim();
    // A search that fails or is superseded must never leave stale results or the
    // "No matching place" hint behind: reset both before each new query.
    setResults([]);
    setSearched(false);
    setError(null);
    setBusy(false);
    if (q.length < MIN_CHARS) {
      return undefined;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy(true);
      try {
        const res = await api("/v1/geocode/search", {
          params: { q, limit: 8, near_lat: near?.lat, near_lon: near?.lon },
          signal: controller.signal,
        });
        setResults(res.results);
        setSearched(true);
        setOpen(true);
        setActive(res.results.length ? 0 : -1);
      } catch (err) {
        if (err.name === "AbortError") return;
        setError(searchErrorMessage(err));
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, near]);

  function choose(r) {
    typed.current = false;
    setText(r.label);
    setOpen(false);
    onChange({ lat: r.lat, lon: r.lon, label: r.name || r.label });
  }

  function onKeyDown(e) {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) {
      setError("Location is not available in this browser.");
      return;
    }
    setBusy(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords;
        try {
          const rev = await api("/v1/geocode/reverse", { params: { lat, lon } });
          if (!rev.within_bengaluru) setError("Your location is outside the Bengaluru service area.");
          choose({ lat, lon, name: "My location", label: `My location (${rev.label})` });
        } catch {
          choose({ lat, lon, name: "My location", label: "My location" });
        } finally {
          setBusy(false);
        }
      },
      (err) => {
        setBusy(false);
        setError(err.code === 1 ? "Location permission denied." : "Could not get your location.");
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  return (
    <div className="place-search">
      <label className="field-label" htmlFor={`${listId}-input`}>
        {label}
      </label>
      <div className="place-row">
        <input
          id={`${listId}-input`}
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder="Search a place, address or 12.97, 77.59"
          value={text}
          onChange={(e) => {
            typed.current = true;
            setText(e.target.value);
          }}
          onKeyDown={onKeyDown}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
        />
        <button type="button" className="icon-btn" title="Use my location" aria-label={`${label}: use my location`} onClick={useMyLocation}>
          ◎
        </button>
        {onPickOnMap && (
          <button
            type="button"
            className={`icon-btn ${picking ? "active" : ""}`}
            title="Pick on map"
            aria-label={`${label}: pick on map`}
            aria-pressed={Boolean(picking)}
            onClick={onPickOnMap}
          >
            ⌖
          </button>
        )}
      </div>
      {busy && <div className="hint">Searching…</div>}
      {error && <div className="hint error">{error}</div>}
      {open && results.length > 0 && (
        <ul className="suggestions" id={listId} role="listbox">
          {results.map((r, i) => (
            <li
              key={r.id}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={() => choose(r)}
            >
              <span className="s-name">{r.name}</span>
              <span className="s-meta">
                {r.category_label}
                {r.address ? ` · ${r.address}` : r.locality ? ` · ${r.locality}` : ""}
                {r.distance_m != null ? ` · ${(r.distance_m / 1000).toFixed(1)} km` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {typed.current && !busy && !error && text.trim().length > 0 && text.trim().length < MIN_CHARS && (
        <div className="hint">Type at least {MIN_CHARS} characters to search.</div>
      )}
      {open && searched && !busy && !error && results.length === 0 && (
        <div className="hint">No matching place in Bengaluru. Try another name or pick on the map.</div>
      )}
    </div>
  );
}
