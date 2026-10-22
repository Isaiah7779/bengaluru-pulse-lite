import { API_BASE_URL } from "../config";

const TOKEN_KEY = "pulse.token";

export function getToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode): session-only auth */
  }
}

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

/** Call the backend; throws ApiError with the server's safe message on failure. */
export async function api(path, { method = "GET", body, params, signal, auth = true } = {}) {
  const url = new URL(API_BASE_URL + path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach the Bengaluru Pulse server. Check your connection.");
  }
  if (response.status === 204) return null;
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const err = data && data.error;
    const fieldMsg =
      err && err.code === "validation_error" && Array.isArray(err.fields) && err.fields.length
        ? err.fields.map((f) => `${f.loc.filter((x) => x !== "body").join(".")}: ${f.msg}`).join("; ")
        : null;
    const message =
      fieldMsg ||
      (err && err.message) ||
      (typeof (data && data.detail) === "string" ? data.detail : null) ||
      `Request failed (HTTP ${response.status})`;
    if (response.status === 401 && token && onUnauthorized) onUnauthorized();
    throw new ApiError(response.status, err ? err.code : `http_${response.status}`, message, err && err.fields);
  }
  return data;
}
