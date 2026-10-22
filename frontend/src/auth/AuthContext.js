import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, getToken, setToken, setTokenProvider, setUnauthorizedHandler } from "../api/client";
import { authMessage, firebaseEnabled, loadFirebase } from "./firebase";

const AuthContext = createContext(null);

// status: "loading" | "signedOut" | "unverified" | "link" | "error" | "ready"
//   unverified  Firebase e-mail/password account whose address is not verified yet
//   link        an older Bengaluru Pulse account uses this e-mail; the owner must link it
//   ready       backend profile loaded (role comes from the server, never from the client)

export function passwordProblems(pw) {
  const problems = [];
  if (pw.length < 10) problems.push("at least 10 characters");
  if (pw.toLowerCase() === pw || pw.toUpperCase() === pw) problems.push("upper- and lower-case letters");
  if (!/\d/.test(pw)) problems.push("a digit");
  return problems;
}

export function AuthProvider({ children }) {
  const mode = firebaseEnabled ? "firebase" : "legacy";
  const [state, setState] = useState(() => ({
    status: mode === "legacy" && !getToken() ? "signedOut" : "loading",
    user: null,
    email: null,
    error: null,
  }));
  const fb = useRef(null);

  const set = useCallback((patch) => setState((s) => ({ ...s, ...patch })), []);

  // ---- shared: load the backend profile for the current credentials ----------------
  const loadProfile = useCallback(async () => {
    try {
      const user = await api("/v1/auth/me");
      set({ status: "ready", user, error: null });
    } catch (err) {
      if (err instanceof ApiError && err.code === "account_link_required") set({ status: "link", user: null, error: null });
      else if (err instanceof ApiError && err.code === "email_not_verified") set({ status: "unverified", user: null });
      else if (err instanceof ApiError && err.status === 401) set({ status: "signedOut", user: null, error: err.message });
      else set({ status: "error", user: null, error: err.message });
    }
  }, [set]);

  // ---- Firebase mode ------------------------------------------------------------------
  useEffect(() => {
    if (mode !== "firebase") return undefined;
    let unsubscribe = () => {};
    let alive = true;
    loadFirebase()
      .then((sdk) => {
        if (!alive) return;
        fb.current = sdk;
        setTokenProvider(async (force) => (sdk.auth.currentUser ? sdk.auth.currentUser.getIdToken(Boolean(force)) : null));
        unsubscribe = sdk.A.onAuthStateChanged(sdk.auth, (fbUser) => {
          if (!fbUser) return set({ status: "signedOut", user: null, email: null });
          set({ email: fbUser.email });
          if (!fbUser.emailVerified) return set({ status: "unverified", user: null });
          set({ status: "loading" });
          loadProfile();
        });
      })
      .catch((err) => alive && set({ status: "error", error: `Sign-in could not start: ${err.message}` }));
    return () => {
      alive = false;
      unsubscribe();
    };
  }, [mode, set, loadProfile]);

  // ---- legacy mode (built-in accounts; used until Firebase is configured) ----------------
  useEffect(() => {
    if (mode !== "legacy" || !getToken()) return;
    loadProfile();
  }, [mode, loadProfile]);

  const signOutLocal = useCallback(
    (reason) => {
      setToken(null);
      set({ status: "signedOut", user: null, error: reason === "token_expired" ? "Your session expired. Sign in again." : null });
    },
    [set]
  );

  useEffect(() => {
    setUnauthorizedHandler((code) => {
      if (mode === "legacy") signOutLocal(code);
      else if (fb.current) fb.current.A.signOut(fb.current.auth);
    });
  }, [mode, signOutLocal]);

  // ---- actions ----------------------------------------------------------------------------
  const withSdk = useCallback(async (fn) => {
    const sdk = fb.current || (await loadFirebase());
    try {
      return await fn(sdk);
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new Error(authMessage(err));
    }
  }, []);

  const signIn = useCallback(
    async (email, password) => {
      if (mode === "legacy") {
        const res = await api("/v1/auth/login", { method: "POST", body: { email, password }, auth: false });
        setToken(res.access_token);
        set({ status: "ready", user: res.user, error: null });
        return;
      }
      await withSdk(({ auth, A }) => A.signInWithEmailAndPassword(auth, email.trim(), password));
    },
    [mode, set, withSdk]
  );

  const register = useCallback(
    async (email, password, displayName) => {
      const problems = passwordProblems(password);
      if (problems.length) throw new Error(`Password needs ${problems.join(", ")}.`);
      if (mode === "legacy") {
        const res = await api("/v1/auth/register", { method: "POST", body: { email, password, display_name: displayName }, auth: false });
        setToken(res.access_token);
        set({ status: "ready", user: res.user, error: null });
        return;
      }
      await withSdk(async ({ auth, A }) => {
        const cred = await A.createUserWithEmailAndPassword(auth, email.trim(), password);
        if (displayName) await A.updateProfile(cred.user, { displayName: displayName.trim() });
        await A.sendEmailVerification(cred.user);
      });
    },
    [mode, set, withSdk]
  );

  const signInWithGoogle = useCallback(
    () =>
      withSdk(async ({ auth, A }) => {
        const provider = new A.GoogleAuthProvider();
        provider.setCustomParameters({ prompt: "select_account" });
        try {
          await A.signInWithPopup(auth, provider);
        } catch (err) {
          if (err.code === "auth/popup-blocked") await A.signInWithRedirect(auth, provider);
          else throw err;
        }
      }),
    [withSdk]
  );

  const resendVerification = useCallback(
    () => withSdk(({ auth, A }) => auth.currentUser && A.sendEmailVerification(auth.currentUser)),
    [withSdk]
  );

  const refreshVerification = useCallback(
    () =>
      withSdk(async ({ auth }) => {
        const u = auth.currentUser;
        if (!u) return false;
        await u.reload();
        if (!u.emailVerified) return false;
        await u.getIdToken(true); // new token carries email_verified=true
        set({ status: "loading" });
        await loadProfile();
        return true;
      }),
    [withSdk, set, loadProfile]
  );

  const resetPassword = useCallback((email) => withSdk(({ auth, A }) => A.sendPasswordResetEmail(auth, email.trim())), [withSdk]);

  const linkAccount = useCallback(
    async (email, password) => {
      const user = await api("/v1/auth/link", { method: "POST", body: { email, password } });
      set({ status: "ready", user, error: null });
    },
    [set]
  );

  const refreshProfile = useCallback(() => loadProfile(), [loadProfile]);

  const logout = useCallback(async () => {
    if (mode === "legacy") {
      try {
        await api("/v1/auth/logout", { method: "POST" });
      } catch {
        /* token may already be invalid */
      }
      signOutLocal();
      return;
    }
    const sdk = fb.current;
    if (sdk) await sdk.A.signOut(sdk.auth);
    set({ status: "signedOut", user: null, email: null, error: null });
  }, [mode, set, signOutLocal]);

  const value = useMemo(
    () => ({
      mode,
      ...state,
      loading: state.status === "loading",
      isAdmin: state.user?.role === "admin",
      firebase: () => fb.current || loadFirebase(),
      signIn,
      login: signIn,
      register,
      signInWithGoogle,
      resendVerification,
      refreshVerification,
      resetPassword,
      linkAccount,
      refreshProfile,
      logout,
    }),
    [mode, state, signIn, register, signInWithGoogle, resendVerification, refreshVerification, resetPassword, linkAccount, refreshProfile, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
