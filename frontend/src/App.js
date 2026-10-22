import { useEffect, useState } from "react";
import "@fontsource-variable/space-grotesk";
import "@fontsource/dm-serif-display";
import "@fontsource/dm-serif-display/400-italic.css";
import "leaflet/dist/leaflet.css";
import "./App.css";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import AuthScreen from "./components/AuthScreen";
import Icon from "./components/Icons";
import AccountPage from "./pages/AccountPage";
import AdminPage from "./pages/AdminPage";
import NavigatePage from "./pages/NavigatePage";
import TrafficPage from "./pages/TrafficPage";

const PAGES = {
  navigate: { label: "Navigate", icon: "compass" },
  traffic: { label: "Traffic", icon: "pulse" },
  account: { label: "My account", icon: "user" },
  admin: { label: "Admin", icon: "shield" },
};

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
  const { user, isAdmin, logout, status } = useAuth();
  const [page, go] = useHashPage();

  // Every page needs a signed-in, verified account. The hash is left untouched while the
  // sign-in screen shows, so the user lands on the page they were heading to.
  if (status !== "ready" || !user) return <AuthScreen />;

  const allowed = (p) => p === "navigate" || p === "traffic" || p === "account" || (p === "admin" && isAdmin);
  const current = PAGES[page] && allowed(page) ? page : "navigate";

  return (
    <div className="shell">
      <aside className="rail">
        <a className="rail-mark" href="#/navigate" aria-label="Bengaluru Pulse home">
          <span aria-hidden="true">B</span>
          <span aria-hidden="true">P</span>
        </a>
        <nav className="rail-nav" aria-label="Main">
          {Object.entries(PAGES)
            .filter(([key]) => allowed(key))
            .map(([key, { label, icon }]) => (
              <a key={key} href={`#/${key}`} className={current === key ? "on" : ""} aria-current={current === key ? "page" : undefined}>
                <Icon name={icon} />
                <span className="rail-label">{label}</span>
              </a>
            ))}
        </nav>
        <div className="rail-foot" aria-hidden="true">
          <span>Est. 2026</span>
        </div>
      </aside>

      <div className="main">
        <header className="topline">
          <a className="brand" href="#/navigate">
            Bengaluru Pulse
          </a>
          <span className="tagline">A calmer city tomorrow</span>
          <div className="user-area">
            <span className="who" title={user.email}>
              {user.display_name}
              {isAdmin && <span className="badge badge-admin">admin</span>}
            </span>
            <button
              className="ghost-btn"
              onClick={async () => {
                await logout();
                go("navigate");
              }}
            >
              <Icon name="logout" size={18} />
              <span>Sign out</span>
            </button>
          </div>
        </header>
        <div className="page-host" key={current}>
          {current === "navigate" && <NavigatePage />}
          {current === "traffic" && <TrafficPage />}
          {current === "account" && <AccountPage />}
          {current === "admin" && <AdminPage />}
        </div>
      </div>
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
