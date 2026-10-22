import { useEffect, useState } from "react";
import "leaflet/dist/leaflet.css";
import "./App.css";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import AuthDialog from "./components/AuthDialog";
import AccountPage from "./pages/AccountPage";
import AdminPage from "./pages/AdminPage";
import NavigatePage from "./pages/NavigatePage";
import TrafficPage from "./pages/TrafficPage";

const PAGES = { navigate: "Navigate", traffic: "Traffic", account: "My account", admin: "Admin" };

function useHashPage() {
  const read = () => (window.location.hash.replace("#/", "") || "navigate").split("?")[0];
  const [page, setPage] = useState(read);
  useEffect(() => {
    const onHash = () => setPage(read());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [page, (p) => (window.location.hash = `#/${p}`)];
}

function Shell() {
  const { user, isAdmin, logout, loading } = useAuth();
  const [page, go] = useHashPage();
  const [showAuth, setShowAuth] = useState(false);

  const allowed = (p) => p === "navigate" || p === "traffic" || (p === "account" && user) || (p === "admin" && isAdmin);
  const current = PAGES[page] && allowed(page) ? page : "navigate";

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/navigate">
          <span className="logo" aria-hidden="true">◉</span> Bengaluru Pulse
        </a>
        <nav aria-label="Main">
          {Object.entries(PAGES)
            .filter(([key]) => allowed(key))
            .map(([key, label]) => (
              <a key={key} href={`#/${key}`} className={current === key ? "on" : ""} aria-current={current === key ? "page" : undefined}>
                {label}
              </a>
            ))}
        </nav>
        <div className="user-area">
          {loading ? null : user ? (
            <>
              <span className="who" title={user.email}>
                {user.display_name}
                {isAdmin && <span className="badge badge-admin">admin</span>}
              </span>
              <button
                className="link-btn"
                onClick={async () => {
                  await logout();
                  go("navigate");
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <button className="primary small" onClick={() => setShowAuth(true)}>
              Sign in
            </button>
          )}
        </div>
      </header>
      {current === "navigate" && <NavigatePage />}
      {current === "traffic" && <TrafficPage />}
      {current === "account" && <AccountPage />}
      {current === "admin" && <AdminPage />}
      {showAuth && <AuthDialog onClose={() => setShowAuth(false)} />}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
