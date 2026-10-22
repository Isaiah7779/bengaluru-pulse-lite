// Sign-in state for the native app. Same rules as the web app:
//   Firebase mode — e-mail/password (verified e-mail required), native Google sign-in,
//   password reset; the backend profile (and role) comes from /v1/auth/me.
//   Legacy mode  — built-in accounts, used only while a build has no Firebase config.
import { GoogleSignin, isErrorWithCode, isSuccessResponse, statusCodes } from "@react-native-google-signin/google-signin";
import {
  createUserWithEmailAndPassword,
  GoogleAuthProvider,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithCredential,
  signInWithEmailAndPassword,
  signOut,
  updateProfile,
} from "firebase/auth";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, loadServerOverride, loadToken, saveToken, setSessionEndedHandler, setTokenProvider } from "./api";
import { authMessage, firebaseAuth, firebaseEnabled, GOOGLE_WEB_CLIENT_ID } from "./firebase";

export type User = { id: number; email: string; display_name: string; role: string; created_at?: string };
export type Status = "loading" | "signedOut" | "unverified" | "link" | "error" | "ready";

type AuthValue = {
  mode: "firebase" | "legacy";
  status: Status;
  user: User | null;
  email: string | null;
  error: string | null;
  googleAvailable: boolean;
  signIn(email: string, password: string): Promise<void>;
  register(email: string, password: string, name: string): Promise<void>;
  signInWithGoogle(): Promise<void>;
  resendVerification(): Promise<void>;
  refreshVerification(): Promise<boolean>;
  resetPassword(email: string): Promise<void>;
  linkAccount(email: string, password: string): Promise<void>;
  reload(): Promise<void>;
  logout(): Promise<void>;
};

const Ctx = createContext<AuthValue | null>(null);

export function passwordProblems(pw: string): string[] {
  const p: string[] = [];
  if (pw.length < 10) p.push("at least 10 characters");
  if (pw.toLowerCase() === pw || pw.toUpperCase() === pw) p.push("upper- and lower-case letters");
  if (!/\d/.test(pw)) p.push("a digit");
  return p;
}

const wrap = async <T,>(fn: () => Promise<T>): Promise<T> => {
  try {
    return await fn();
  } catch (e: any) {
    if (e instanceof ApiError) throw e;
    throw new Error(authMessage(e));
  }
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const mode = firebaseEnabled ? "firebase" : "legacy";
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    try {
      const me = await api<User>("/v1/auth/me");
      setUser(me);
      setError(null);
      setStatus("ready");
    } catch (e: any) {
      setUser(null);
      if (e instanceof ApiError && e.code === "account_link_required") setStatus("link");
      else if (e instanceof ApiError && e.code === "email_not_verified") setStatus("unverified");
      else if (e instanceof ApiError && e.status === 401) {
        setError(e.message);
        setStatus("signedOut");
      } else {
        // e.g. no server address yet: show the message on the sign-in screen.
        setError(e.message);
        setStatus("error");
      }
    }
  }, []);

  useEffect(() => {
    let unsubscribe = () => {};
    setSessionEndedHandler(() => {
      if (mode === "firebase") signOut(firebaseAuth()).catch(() => null);
      else {
        setUser(null);
        setStatus("signedOut");
      }
    });
    loadServerOverride()
      .catch(() => null)
      .then(async () => {
        if (mode === "legacy") {
          const t = await loadToken();
          if (t) await loadProfile();
          else setStatus("signedOut");
          return;
        }
        if (GOOGLE_WEB_CLIENT_ID) GoogleSignin.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
        const auth = firebaseAuth();
        setTokenProvider(async (force) => (auth.currentUser ? auth.currentUser.getIdToken(force) : null));
        unsubscribe = onAuthStateChanged(auth, (fbUser) => {
          if (!fbUser) {
            setUser(null);
            setEmail(null);
            setStatus("signedOut");
            return;
          }
          setEmail(fbUser.email);
          if (!fbUser.emailVerified) {
            setStatus("unverified");
            return;
          }
          setStatus("loading");
          loadProfile();
        });
      });
    return () => unsubscribe();
  }, [mode, loadProfile]);

  const value = useMemo<AuthValue>(
    () => ({
      mode,
      status,
      user,
      email,
      error,
      googleAvailable: mode === "firebase" && Boolean(GOOGLE_WEB_CLIENT_ID),
      async signIn(mail, password) {
        if (mode === "legacy") {
          const res = await api("/v1/auth/login", { method: "POST", body: { email: mail, password } });
          await saveToken(res.access_token);
          setUser(res.user);
          setStatus("ready");
          return;
        }
        await wrap(() => signInWithEmailAndPassword(firebaseAuth(), mail.trim(), password));
      },
      async register(mail, password, name) {
        const problems = passwordProblems(password);
        if (problems.length) throw new Error(`Password needs ${problems.join(", ")}.`);
        if (mode === "legacy") {
          const res = await api("/v1/auth/register", { method: "POST", body: { email: mail, password, display_name: name } });
          await saveToken(res.access_token);
          setUser(res.user);
          setStatus("ready");
          return;
        }
        await wrap(async () => {
          const cred = await createUserWithEmailAndPassword(firebaseAuth(), mail.trim(), password);
          if (name.trim()) await updateProfile(cred.user, { displayName: name.trim() });
          await sendEmailVerification(cred.user);
        });
      },
      async signInWithGoogle() {
        await wrap(async () => {
          try {
            await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
            const res = await GoogleSignin.signIn();
            if (!isSuccessResponse(res)) return; // cancelled by the user
            const idToken = res.data.idToken;
            if (!idToken) throw new Error("Google did not return an ID token (check EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID).");
            await signInWithCredential(firebaseAuth(), GoogleAuthProvider.credential(idToken));
          } catch (e: any) {
            if (isErrorWithCode(e) && e.code === statusCodes.IN_PROGRESS) return;
            if (isErrorWithCode(e) && e.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) throw new Error("Google Play services are not available on this device.");
            throw e;
          }
        });
      },
      async resendVerification() {
        const u = firebaseAuth().currentUser;
        if (u) await wrap(() => sendEmailVerification(u));
      },
      async refreshVerification() {
        const u = firebaseAuth().currentUser;
        if (!u) return false;
        await wrap(() => u.reload());
        if (!u.emailVerified) return false;
        await u.getIdToken(true);
        setStatus("loading");
        await loadProfile();
        return true;
      },
      async resetPassword(mail) {
        await wrap(() => sendPasswordResetEmail(firebaseAuth(), mail.trim()));
      },
      async linkAccount(mail, password) {
        const me = await api<User>("/v1/auth/link", { method: "POST", body: { email: mail, password } });
        setUser(me);
        setStatus("ready");
      },
      reload: loadProfile,
      async logout() {
        if (mode === "legacy") {
          await api("/v1/auth/logout", { method: "POST" }).catch(() => null);
          await saveToken(null);
          setUser(null);
          setStatus("signedOut");
          return;
        }
        if (GOOGLE_WEB_CLIENT_ID) await GoogleSignin.signOut().catch(() => null);
        await signOut(firebaseAuth());
      },
    }),
    [mode, status, user, email, error, loadProfile]
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
