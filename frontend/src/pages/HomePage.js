import HeroArt from "../components/HeroArt";
import Icon from "../components/Icons";
import { IncidentCard, TrafficCard, WeatherCard } from "../components/InsightStrip";

const PROBLEMS = [
  ["pulse", "Unpredictable congestion", "The same trip can take very different times depending on the hour, the weather and incidents on the way."],
  ["route", "Routes need comparing", "The usual way is not always the quickest; you need several real alternatives side by side, timed the same way."],
  ["cloud", "Weather changes the picture", "Rain slows the city. Traffic numbers mean more when you can see the weather alongside them."],
  ["layers", "Scattered, hard-to-read data", "Speeds at individual points are hard to interpret without context: how slow is slow, compared with what, and how recently?"],
];

const SOLUTION = [
  ["pulse", "Live traffic monitoring", "TomTom flow readings at monitored corridor points, collected every 30 minutes and marked stale when old."],
  ["route", "Route planning and comparison", "Up to five routes over the OpenStreetMap road network for car, motorcycle, bicycle and walking, each with its source shown."],
  ["cloud", "Weather context", "Current conditions from Open-Meteo for the city and monitored areas, shown next to the traffic data."],
  ["chart", "Traffic analytics", "Trends and comparisons built only from the observations this system has actually stored."],
  ["compass", "On your phone", "The web app works on phones, and an Android app uses the same account and server."],
];

const DESTINATIONS = [
  ["#/navigate", "compass", "Navigate", "Plan and compare routes on the live map."],
  ["#/traffic", "pulse", "Traffic", "Monitored points, incidents and weather right now."],
  ["#/insights", "chart", "Insights", "Trends and comparisons from stored observations."],
  ["#/journal", "book", "Journal", "Your saved journeys and personal notes."],
  ["#/about", "info", "About us", "How Bengaluru Pulse works and its limits."],
];

export default function HomePage() {
  return (
    <div className="page home-page">
      <section className="home-hero">
        <div className="home-hero-copy">
          <p className="eyebrow">Bengaluru Pulse · Home</p>
          <h2 className="page-title home-title">
            Move smarter. <em>Understand Bengaluru.</em>
          </h2>
          <p className="page-lede">
            Live traffic at monitored corridors, comparable routes across the whole road network, and the weather in between: in one place,
            with every number traceable to its source.
          </p>
          <div className="home-actions">
            <a className="button-link primary-link" href="#/navigate">
              Explore the app <Icon name="arrow" size={18} />
            </a>
            <a className="button-link" href="#/about">
              How it works
            </a>
          </div>
        </div>
        <HeroArt />
      </section>

      <section aria-labelledby="home-live">
        <div className="section-head">
          <p className="eyebrow">Right now</p>
          <h3 id="home-live">The city at a glance</h3>
        </div>
        <div className="home-live">
          <TrafficCard />
          <IncidentCard />
          <WeatherCard />
        </div>
      </section>

      <section aria-labelledby="home-problem" className="home-split">
        <div className="section-head">
          <p className="eyebrow">The problem</p>
          <h3 id="home-problem">Getting around Bengaluru is hard to predict.</h3>
        </div>
        <div className="feature-grid">
          {PROBLEMS.map(([icon, title, text]) => (
            <article className="feature-card" key={title}>
              <Icon name={icon} size={22} />
              <h4>{title}</h4>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section aria-labelledby="home-solution" className="home-split">
        <div className="section-head">
          <p className="eyebrow">What Bengaluru Pulse does</p>
          <h3 id="home-solution">Evidence first, then a recommendation.</h3>
        </div>
        <div className="feature-grid">
          {SOLUTION.map(([icon, title, text]) => (
            <article className="feature-card feature-card--solution" key={title}>
              <Icon name={icon} size={22} />
              <h4>{title}</h4>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section aria-labelledby="home-go">
        <div className="section-head">
          <p className="eyebrow">Where to next</p>
          <h3 id="home-go">Explore the app</h3>
        </div>
        <nav className="dest-grid" aria-label="Bengaluru Pulse sections">
          {DESTINATIONS.map(([href, icon, title, text]) => (
            <a className="dest-card" href={href} key={href}>
              <Icon name={icon} size={22} />
              <span className="dest-title">{title}</span>
              <span className="dest-text">{text}</span>
              <Icon name="arrow" size={18} className="dest-arrow" />
            </a>
          ))}
        </nav>
      </section>
    </div>
  );
}
