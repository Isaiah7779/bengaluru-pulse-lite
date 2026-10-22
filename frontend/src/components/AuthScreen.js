import { useState } from "react";
import { useAuth } from "../auth/AuthContext";
import CityArt from "./CityArt";
import Icon from "./Icons";

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const run = async (fn, okMessage) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const result = await fn();
      if (okMessage) setInfo(typeof okMessage === "function" ? okMessage(result) : okMessage);
      return result;
    } catch (err) {
      setError(err.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, info, setError, setInfo, run };
}

function Messages({ error, info }) {
  return (
    <>
      {error && (
        <div className="error-box" role="alert">
          {error}
        </div>
      )}
      {info && (
        <div className="note" role="status">
          {info}
        </div>
      )}
    </>
  );
}

function SignInForm({ view, setView }) {
  const auth = useAuth();
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const { busy, error, info, run } = useAction();
  const registering = view === "register";
  const resetting = view === "reset";
  const firebase = auth.mode === "firebase";

  async function submit(e) {
    e.preventDefault();
    if (resetting) {
      await run(() => auth.resetPassword(form.email), "If an account exists for that address, a reset link is on its way. Check your inbox.");
      return;
    }
    await run(() => (registering ? auth.register(form.email, form.password, form.name) : auth.signIn(form.email, form.password)));
  }

  const title = resetting ? "Reset your password" : registering ? "Create your account" : "Welcome back";
  return (
    <>
      <p className="eyebrow">{resetting ? "Account recovery" : registering ? "Join Bengaluru Pulse" : "Sign in"}</p>
      <h2 className="auth-title">{title}</h2>
      <form className="stack-form auth-form" onSubmit={submit}>
        {registering && (
          <label>
            Your name
            <input required maxLength={80} autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
        )}
        <label>
          E-mail
          <input
            required
            type="email"
            autoComplete="email"
            inputMode="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </label>
        {!resetting && (
          <label>
            Password
            <input
              required
              type="password"
              autoComplete={registering ? "new-password" : "current-password"}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </label>
        )}
        {registering && <div className="hint">At least 10 characters with upper- and lower-case letters and a digit.</div>}
        <button className="primary plan-btn" disabled={busy}>
          {busy ? <span className="spinner" aria-hidden="true" /> : null}
          {resetting ? "Send reset link" : registering ? "Create account" : "Sign in"}
        </button>
        <Messages error={error || (!registering && !resetting ? auth.error : null)} info={info} />
      </form>

      {firebase && !resetting && (
        <>
          <div className="auth-or">
            <span>or</span>
          </div>
          <button type="button" className="google-btn" disabled={busy} onClick={() => run(auth.signInWithGoogle)}>
            <GoogleMark /> Continue with Google
          </button>
        </>
      )}

      <div className="auth-switch">
        {view === "signin" ? (
          <>
            <span>New here?</span>
            <button type="button" className="link-btn" onClick={() => setView("register")}>
              Create an account
            </button>
            {firebase && (
              <button type="button" className="link-btn" onClick={() => setView("reset")}>
                Forgot password?
              </button>
            )}
          </>
        ) : (
          <>
            <span>{registering ? "Already registered?" : "Remembered it?"}</span>
            <button type="button" className="link-btn" onClick={() => setView("signin")}>
              Sign in
            </button>
          </>
        )}
      </div>
    </>
  );
}

function VerifyEmail() {
  const auth = useAuth();
  const { busy, error, info, setInfo, run } = useAction();
  return (
    <>
      <p className="eyebrow">One more step</p>
      <h2 className="auth-title">Verify your e-mail</h2>
      <p className="auth-lede">
        We sent a verification link to <b>{auth.email}</b>. Open it, then come back here. Bengaluru Pulse stays locked until the address is verified.
      </p>
      <div className="stack-form auth-form">
        <button
          type="button"
          className="primary plan-btn"
          disabled={busy}
          onClick={async () => {
            const ok = await run(auth.refreshVerification);
            if (ok === false) setInfo("Not verified yet. Open the link in the e-mail, then try again.");
          }}
        >
          {busy && <span className="spinner" aria-hidden="true" />} I've verified — continue
        </button>
        <button type="button" disabled={busy} onClick={() => run(auth.resendVerification, "Verification e-mail sent again. Check spam if it does not arrive.")}>
          Resend verification e-mail
        </button>
        <button type="button" className="link-btn" onClick={auth.logout}>
          Use a different account
        </button>
        <Messages error={error} info={info} />
      </div>
    </>
  );
}

function LinkAccount() {
  const auth = useAuth();
  const [form, setForm] = useState({ email: auth.email || "", password: "" });
  const { busy, error, run } = useAction();
  return (
    <>
      <p className="eyebrow">Existing account found</p>
      <h2 className="auth-title">Link your account</h2>
      <p className="auth-lede">
        An earlier Bengaluru Pulse account already uses <b>{auth.email}</b>. Enter that account's old password once to link it. Your trips, role and
        history stay with it. An e-mail match alone is never enough to merge accounts.
      </p>
      <form
        className="stack-form auth-form"
        onSubmit={(e) => {
          e.preventDefault();
          run(() => auth.linkAccount(form.email, form.password));
        }}
      >
        <label>
          Old account e-mail
          <input required type="email" autoComplete="username" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label>
          Old account password
          <input required type="password" autoComplete="current-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        <button className="primary plan-btn" disabled={busy}>
          {busy && <span className="spinner" aria-hidden="true" />} Link and continue
        </button>
        <button type="button" className="link-btn" onClick={auth.logout}>
          Sign out
        </button>
        <Messages error={error} />
      </form>
    </>
  );
}

function AuthError() {
  const auth = useAuth();
  return (
    <>
      <p className="eyebrow">Sign-in problem</p>
      <h2 className="auth-title">We couldn't open your account</h2>
      <Messages error={auth.error} />
      <div className="stack-form auth-form">
        <button type="button" className="primary plan-btn" onClick={auth.refreshProfile}>
          Try again
        </button>
        <button type="button" className="link-btn" onClick={auth.logout}>
          Sign out
        </button>
      </div>
    </>
  );
}

export default function AuthScreen() {
  const auth = useAuth();
  const [view, setView] = useState("signin");
  let body;
  if (auth.status === "loading") body = <div className="skeleton" style={{ height: 240 }} aria-label="Loading your account" />;
  else if (auth.status === "unverified") body = <VerifyEmail />;
  else if (auth.status === "link") body = <LinkAccount />;
  else if (auth.status === "error") body = <AuthError />;
  else body = <SignInForm view={view} setView={setView} />;

  return (
    <main className="auth-page">
      <section className="auth-art" aria-hidden="true">
        <CityArt />
        <div className="auth-art-copy">
          <span className="rail-mark">
            <span>B</span>
            <span>P</span>
          </span>
          <p className="auth-art-title">
            Move smarter. <em>Bengaluru.</em>
          </p>
          <p className="auth-art-sub">Live traffic. Smarter routes. Clearer decisions. A calmer city, together.</p>
        </div>
      </section>
      <section className="auth-panel">
        <div className="auth-brand">
          <span className="brand">Bengaluru Pulse</span>
          <span className="tagline">A calmer city tomorrow</span>
        </div>
        <div className="auth-card">{body}</div>
        <p className="auth-fine">
          <Icon name="shield" size={14} /> Your sign-in is handled by {auth.mode === "firebase" ? "Firebase Authentication" : "Bengaluru Pulse"}. Passwords are never
          stored in your browser.
        </p>
      </section>
    </main>
  );
}
