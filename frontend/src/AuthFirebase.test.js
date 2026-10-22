import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

// Firebase-mode UI with a stand-in SDK (the real SDK, rules and backend verification are
// covered by firebase/tests and backend/tests/test_firebase_auth.py).
jest.mock("./components/MapView", () => () => <div data-testid="map" />);

const mockSdk = {
  auth: { currentUser: null },
  A: {
    onAuthStateChanged: jest.fn(),
    sendEmailVerification: jest.fn(async () => {}),
    signOut: jest.fn(async () => {}),
    signInWithEmailAndPassword: jest.fn(),
    GoogleAuthProvider: function GoogleAuthProvider() {
      this.setCustomParameters = () => {};
    },
    signInWithPopup: jest.fn(async () => {}),
  },
  F: {},
  db: {},
};

jest.mock("./auth/firebase", () => ({
  firebaseEnabled: true,
  USE_EMULATOR: false,
  loadFirebase: () => Promise.resolve(mockSdk),
  authMessage: (e) => e.message,
}));
jest.mock("./data/personal", () => ({
  getPreferences: async () => null,
  listFavorites: async () => [],
}));

function signedInAs(user) {
  mockSdk.auth.currentUser = user;
  mockSdk.A.onAuthStateChanged.mockImplementation((auth, cb) => {
    cb(user);
    return () => {};
  });
}

function fbUser({ verified }) {
  return {
    uid: "u1",
    email: "asha@pulse.example",
    emailVerified: verified,
    reload: jest.fn(async () => {}),
    getIdToken: jest.fn(async () => "fb-id-token"),
  };
}

function respond(map) {
  global.fetch = jest.fn(async (url, opts = {}) => {
    const path = new URL(url).pathname;
    const handler = map[`${opts.method || "GET"} ${path}`] || map[path];
    if (!handler) return { ok: false, status: 404, json: async () => ({ error: { code: "not_found", message: path } }) };
    const [status, body] = typeof handler === "function" ? handler(url, opts) : handler;
    return { ok: status < 400, status, json: async () => body };
  });
}

const ME = [200, { id: 7, email: "asha@pulse.example", display_name: "Asha", role: "user", created_at: "2026-10-01T00:00:00Z" }];

beforeEach(() => {
  window.location.hash = "";
  jest.clearAllMocks();
});

test("signed-out visitors get e-mail and Google sign-in", async () => {
  signedInAs(null);
  respond({});
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Continue with Google/ }));
  await waitFor(() => expect(mockSdk.A.signInWithPopup).toHaveBeenCalled());
  expect(screen.getByRole("button", { name: "Forgot password?" })).toBeInTheDocument();
});

test("an unverified e-mail stays on the verification screen", async () => {
  const user = fbUser({ verified: false });
  signedInAs(user);
  respond({});
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Verify your e-mail" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Find routes" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Resend verification e-mail" }));
  await waitFor(() => expect(mockSdk.A.sendEmailVerification).toHaveBeenCalledWith(user));
  expect(await screen.findByText(/sent again/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /verified — continue/ }));
  expect(await screen.findByText(/Not verified yet/)).toBeInTheDocument();
  expect(user.reload).toHaveBeenCalled();
  expect(global.fetch).not.toHaveBeenCalled();
});

test("verified users reach the app and API calls carry the Firebase ID token", async () => {
  signedInAs(fbUser({ verified: true }));
  respond({ "/v1/auth/me": ME, "/v1/vehicles": [200, { vehicles: [] }] });
  render(<App />);
  expect(await screen.findByRole("button", { name: "Find routes" })).toBeInTheDocument();
  const [, opts] = global.fetch.mock.calls.find(([url]) => url.includes("/v1/auth/me"));
  expect(opts.headers.Authorization).toBe("Bearer fb-id-token");
  expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
});

test("an older account with the same e-mail must be linked with its password", async () => {
  signedInAs(fbUser({ verified: true }));
  let linked = false;
  respond({
    "/v1/auth/me": () =>
      linked ? ME : [409, { error: { code: "account_link_required", message: "An existing Bengaluru Pulse account uses this e-mail." } }],
    "POST /v1/auth/link": (url, opts) => {
      expect(JSON.parse(opts.body)).toEqual({ email: "asha@pulse.example", password: "Old-Password-1" });
      linked = true;
      return ME;
    },
    "/v1/vehicles": [200, { vehicles: [] }],
  });
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Link your account" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Old account password"), { target: { value: "Old-Password-1" } });
  fireEvent.click(screen.getByRole("button", { name: /Link and continue/ }));
  expect(await screen.findByRole("button", { name: "Find routes" })).toBeInTheDocument();
});

test("expired Firebase tokens are refreshed once before giving up", async () => {
  const user = fbUser({ verified: true });
  signedInAs(user);
  let calls = 0;
  respond({
    "/v1/auth/me": () => (++calls === 1 ? [401, { error: { code: "token_expired", message: "Session expired" } }] : ME),
    "/v1/vehicles": [200, { vehicles: [] }],
  });
  render(<App />);
  expect(await screen.findByRole("button", { name: "Find routes" })).toBeInTheDocument();
  expect(user.getIdToken).toHaveBeenCalledWith(true);
  expect(mockSdk.A.signOut).not.toHaveBeenCalled();
});

test("a wrong old password shows an error and keeps the user signed in", async () => {
  signedInAs(fbUser({ verified: true }));
  respond({
    "/v1/auth/me": [409, { error: { code: "account_link_required", message: "Link it." } }],
    "POST /v1/auth/link": [401, { error: { code: "invalid_credentials", message: "Incorrect e-mail or password" } }],
  });
  render(<App />);
  fireEvent.change(await screen.findByLabelText("Old account password"), { target: { value: "nope" } });
  fireEvent.click(screen.getByRole("button", { name: /Link and continue/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect e-mail or password");
  expect(mockSdk.A.signOut).not.toHaveBeenCalled();
  expect(screen.getByRole("heading", { name: "Link your account" })).toBeInTheDocument();
});
