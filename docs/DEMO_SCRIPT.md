# Demo script (5–7 minutes)

## Before the review (10 minutes earlier)

1. Start Docker Desktop, then in the project folder: `docker compose up -d`
2. Wait until `docker compose ps` shows backend/osrm/postgres **healthy** (≈ 1 min).
3. Check http://localhost:8000/health/ready — every check `ok`.
4. Open http://localhost:8080 in a browser. In a second tab, sign in as the
   administrator (credentials you created with `auth.bootstrap`; never show them on screen).
5. Have a normal test user ready (or register one live).
6. Keep a terminal open in the project folder.

Live traffic changes, so route labels in the demo can differ from those in this
script. Describe what is on screen; don't promise a shortcut.

## Sequence

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | Home page (Navigate) | "Bengaluru Pulse plans routes on the full OpenStreetMap road network for Bengaluru and explains every number it shows. Nothing is simulated." |
| 0:30–1:30 | **From**: type `Koramangala`, pick the suggestion. **To**: type `Hebbal`, pick *Hebbal – Area*. Mode **Car**, **Fastest**, **Leave now** → *Find routes* | "Search uses our own index of 68,761 OSM places. We generate 10+ candidate routes, remove near-duplicates, and time each one with TomTom traffic on its own geometry." |
| 1:30–2:30 | Recommendation box, route cards, badges; click the reference card, then another | "All routes are compared on one basis — here live TomTom traffic. The *Reference* is OSRM's default route; a *Shortcut* must be shorter **and** faster than it, a *Longcut* longer but faster. The difference is shown in km and minutes." If no shortcut/longcut appears: "Right now no candidate is both shorter and faster, so they are labelled Alternative — the definitions are strict." |
| 2:30–3:15 | *Why this route*: traffic delay, typical time, geometry match %, incidents *on* the route, monitored points; open *Show navigation steps*; open *Data sources* | "Every claim cites its source. If TomTom's timing came from a different road (length mismatch > 8 %), we reject it rather than show a wrong ETA." |
| 3:15–3:45 | Change mode to **Walk** → *Find routes* | "Walking and cycling use their own road graphs — about 5 km/h on footpaths, no car traffic applied." |
| 3:45–4:15 | Departure **Leave at…** +1 h → *Find routes* | "For future departures we use TomTom's prediction and label it as such. Our own forecasting model is not used yet — I'll explain why." |
| 4:15–4:45 | **Traffic** page: monitored points, freshness, incidents, weather, "Pulse forecasts in routing: Off" | "The collector stores real observations every 30 minutes at 26 sample points — samples, not city-wide coverage." |
| 4:45–5:30 | Sign in as user → tick *Save to my trip history* → plan → **My account → Trip history**; mention *Share a route* (3 independent users + admin review) | "Personal data is visible only to its owner; community shortcuts are never verified automatically." |
| 5:30–6:15 | Admin tab: **System health** (TomTom calls used today vs budget), **Models & metrics** | "This is the research result: on the public daily dataset the best model's test error (MAE 16.08) did not beat the historical average (15.99). V1's R² of 0.96 came from using same-day measurements — estimation, not forecasting." |
| 6:15–6:45 | Terminal: `docker compose exec collector python -m forecasting.online report` (or the *Data freshness* tab) | "We now log baseline forecasts prospectively and compare them with what actually happened. Evaluating a real model needs at least 14 days of data — we report this as ongoing, not as a result." |
| 6:45–7:00 | Close | "Working, tested, reproducible system; forecasting infrastructure in place; validated forecasting is future work." |

## Optional (if asked): resilience

```bash
docker compose stop osrm-foot      # walking now returns a clear "routing engine unavailable" error; car still works
docker compose start osrm-foot     # recovers within ~20 s
```

## Fallbacks

| Problem during demo | Do this |
|---|---|
| TomTom quota/key problem | Routes still appear with "Free-flow estimate (OSRM)" and a warning — explain the graceful fallback. |
| Search returns nothing | Type coordinates instead: `12.9352, 77.6245` → `13.0358, 77.5970`. |
| Browser cannot reach the server | `docker compose ps`, `docker compose logs backend --tail 30`; restart with `docker compose up -d`. |
| Network outage | OSRM routing, search and the database are local and keep working; only traffic and weather are missing. |
