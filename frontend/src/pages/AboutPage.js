import { useAuth } from "../auth/AuthContext";
import Icon from "../components/Icons";
import { PROJECT_CONTEXT, TEAM } from "../content/team";

const HOW = [
  ["Collect", "A collector reads TomTom traffic flow at monitored corridor points and Open-Meteo weather every 30 minutes, and TomTom incidents every hour, storing each reading with its time."],
  ["Route", "OSRM computes routes over the OpenStreetMap road network (separate car, foot and bicycle graphs). Car and motorcycle routes are then timed with TomTom using each route's own geometry."],
  ["Compare", "Alternatives are compared on the same time basis and labelled honestly: shortcut, longcut or reference, and live, predicted or free-flow."],
  ["Explain", "Every result lists its data sources and their freshness. Readings older than 90 minutes are marked stale rather than shown as live."],
];

function Stack({ mode }) {
  const rows = [
    ["Web app", "React with Leaflet maps on OpenStreetMap tiles; charts with Recharts."],
    ["API", "FastAPI (Python), with role checks on every protected request."],
    ["Database", "PostgreSQL with PostGIS for observations, routes, incidents and accounts."],
    ["Routing", "OSRM over OpenStreetMap data; place search from a 68,761-place OpenStreetMap index, with Photon as a fallback."],
    ["Traffic", "TomTom Traffic Flow, Incidents and Routing APIs."],
    ["Weather", "Open-Meteo (CC BY 4.0)."],
    [
      "Sign-in",
      mode === "firebase"
        ? "Firebase Authentication (e-mail verification, Google) with tokens checked on the server by the Firebase Admin SDK."
        : "Built-in accounts today; Firebase Authentication is implemented and switches on once the project is configured.",
    ],
    ["Mobile", "An Expo / React Native Android app on the same server and accounts."],
    ["Deployment", "Docker Compose (database, API, collector, routing engines, web server)."],
  ];
  return (
    <dl className="stack-list">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

function Team() {
  const context = [PROJECT_CONTEXT.programme, PROJECT_CONTEXT.institution].filter(Boolean).join(" · ");
  return (
    <section className="panel about-team" aria-labelledby="about-team">
      <div className="panel-head">
        <h3 id="about-team">The team behind Bengaluru Pulse</h3>
        <span className="eyebrow">Major project · Phase 2</span>
      </div>
      {context && <p className="muted">{context}</p>}
      {PROJECT_CONTEXT.guide && <p className="muted">Project guide: {PROJECT_CONTEXT.guide}</p>}
      {TEAM.length ? (
        <ul className="team-grid">
          {TEAM.map((m) => (
            <li className="team-card" key={m.name}>
              <span className="team-avatar" aria-hidden="true">
                {initials(m.name)}
              </span>
              <div>
                <p className="team-name">{m.name}</p>
                {m.role && <p className="team-role">{m.role}</p>}
                {m.contribution && <p className="team-text">{m.contribution}</p>}
                {m.links?.length > 0 && (
                  <p className="team-links">
                    {m.links.map((l) => (
                      <a key={l.href} href={l.href} target="_blank" rel="noreferrer">
                        {l.label}
                      </a>
                    ))}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="team-empty">The project team will be introduced here once their details are confirmed.</p>
      )}
    </section>
  );
}

export default function AboutPage() {
  const { mode } = useAuth();
  return (
    <div className="page about-page">
      <header className="page-head">
        <div>
          <p className="eyebrow">About us</p>
          <h2 className="page-title">
            A calmer city, <em>with evidence.</em>
          </h2>
        </div>
        <p className="page-lede">
          Bengaluru Pulse is a route-planning and traffic-intelligence project for Bengaluru, built as a final-year major project (Phase 2). It
          is meant for commuters who want a clearer view of the roads, and it shows its working for anyone evaluating it.
        </p>
      </header>

      <div className="about-grid">
        <section className="panel" aria-labelledby="about-mission">
          <h3 id="about-mission">Our mission</h3>
          <p>
            Help people choose how and when to travel using information they can trust: measured where it is measured, estimated where it is
            estimated, and never invented.
          </p>
        </section>
        <section className="panel" aria-labelledby="about-problem">
          <h3 id="about-problem">The problem we are addressing</h3>
          <p>
            Congestion in Bengaluru is heavy and changes by the hour and with the weather. Navigation apps rarely explain why a route is
            recommended or whether a travel time was measured, predicted or assumed.
          </p>
        </section>
      </div>

      <section className="panel" aria-labelledby="about-how">
        <h3 id="about-how">How the system works</h3>
        <ol className="how-steps">
          {HOW.map(([title, text], i) => (
            <li key={title}>
              <span className="how-num" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <h4>{title}</h4>
                <p>{text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel" aria-labelledby="about-stack">
        <h3 id="about-stack">Technology</h3>
        <Stack mode={mode} />
      </section>

      <Team />

      <section className="panel about-limits" aria-labelledby="about-limits">
        <h3 id="about-limits">Limitations and transparency</h3>
        <ul className="compact">
          <li>Traffic is measured at a fixed set of monitored corridor points, not across the whole city.</li>
          <li>Live and future travel times come from TomTom's routing service; they are provider estimates, not our own forecasts.</li>
          <li>Our own forecasting models are still being evaluated. None is used for routing until it beats simple baselines on held-out data.</li>
          <li>Walking and cycling routes use dedicated graphs but are timed without live traffic.</li>
          <li>Motorcycle routes use the car road graph; two-wheeler-specific restrictions are not modelled.</li>
          <li>Readings depend on external services and free-tier limits; when data is old or unavailable, the app says so.</li>
        </ul>
      </section>

      <section className="about-cta">
        <p>See it for yourself on the live map.</p>
        <a className="button-link primary-link" href="#/navigate">
          Explore the app <Icon name="arrow" size={18} />
        </a>
      </section>
    </div>
  );
}
