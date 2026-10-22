import { useEffect, useState } from "react";
import "@fontsource-variable/space-grotesk";
import "@fontsource/dm-serif-display";
import "@fontsource/dm-serif-display/400-italic.css";
import "leaflet/dist/leaflet.css";
import "./App.css";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import AuthScreen from "./components/AuthScreen";
import Icon from "./components/Icons";
import AboutPage from "./pages/AboutPage";
import AccountPage from "./pages/AccountPage";
import AdminPage from "./pages/AdminPage";
import HomePage from "./pages/HomePage";
import InsightsPage from "./pages/InsightsPage";
import JournalPage from "./pages/JournalPage";
import NavigatePage from "./pages/NavigatePage";
import TrafficPage from "./pages/TrafficPage";

const PAGES = {
  home: { label: "Home", icon: "home" },
  navigate: { label: "Navigate", icon: "compass" },
  traffic: { label: "Traffic", icon: "pulse" },
  insights: { label: "Insights", icon: "chart" },
  journal: { label: "Journal", icon: "book" },
  about: { label: "About", icon: "info" },
  account: { label: "My account", icon: "user" },
  admin: { label: "Admin", icon: "shield" },
};

function useHashPage() {
  const read = () => (window.location.hash.replace("#/", "") || "home").split("?")[0];
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

  // Every page needs a signed-in user (above); Admin additionally needs the admin role,
  // which the backend enforces again on every admin request.
  const allowed = (p) => p !== "admin" || isAdmin;
  const current = PAGES[page] && allowed(page) ? page : "home";

  return (
    <div className="shell">
      <aside className="rail">
        <a className="rail-mark" href="#/home" aria-label="Bengaluru Pulse home">
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
          <a className="brand" href="#/home">
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
                go("home");
              }}
            >
              <Icon name="logout" size={18} />
              <span>Sign out</span>
            </button>
          </div>
        </header>
        <div className="page-host" key={current}>
          {current === "home" && <HomePage />}
          {current === "navigate" && <NavigatePage />}
          {current === "insights" && <InsightsPage />}
          {current === "journal" && <JournalPage />}
          {current === "about" && <AboutPage />}
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
