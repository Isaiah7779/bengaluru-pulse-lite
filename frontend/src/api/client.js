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

// Where bearer tokens come from: Firebase ID tokens (refreshed by the SDK) when Firebase
// sign-in is active, otherwise the legacy token kept in localStorage.
let tokenProvider = null;
export function setTokenProvider(fn) {
  tokenProvider = fn;
}
async function currentToken(forceRefresh) {
  if (tokenProvider) return tokenProvider(forceRefresh);
  return getToken();
}

/** Call the backend; throws ApiError with the server's safe message on failure. */
export async function api(path, options = {}) {
  try {
    return await request(path, options, false);
  } catch (err) {
    // A Firebase ID token can expire between refreshes (e.g. after sleep): refresh once.
    if (err instanceof ApiError && err.code === "token_expired" && tokenProvider && options.auth !== false) {
      return request(path, options, true);
    }
    throw err;
  }
}

async function request(path, { method = "GET", body, params, signal, auth = true } = {}, forceRefresh) {
  const url = new URL(API_BASE_URL + path, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    });
  }
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = auth ? await currentToken(forceRefresh) : null;
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
    const code = err ? err.code : `http_${response.status}`;
    // A wrong password typed into a form (401 invalid_credentials) is not a dead session.
    const sessionEnded = response.status === 401 && code !== "invalid_credentials";
    if (sessionEnded && token && onUnauthorized && !(code === "token_expired" && tokenProvider && !forceRefresh)) onUnauthorized(code);
    throw new ApiError(response.status, code, message, err && err.fields);
  }
  return data;
}
