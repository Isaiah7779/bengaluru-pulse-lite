# User guide

Open the web app at **http://localhost:8080** (after `docker compose up -d`).
The top bar has **Navigate**, **Traffic**, and, once signed in, **My account**
and (administrators only) **Admin**.

## 1. Plan a route (no account needed)

1. **From**: type a place (e.g. `Koramangala`, `Phoenix Market City`,
   `Indiranagar Metro`) and pick a suggestion with the mouse or ↑/↓ + Enter.
   * Coordinates also work: `12.9352, 77.6245`.
   * ◎ uses your current GPS location (the browser asks for permission).
   * ⌖ then click on the map to pick a point.
2. **To**: same as above. ⇅ swaps start and destination.
3. **Travel mode**: Car, Motorcycle, Bicycle or Walk. A greyed-out mode means its
   routing server is not running. Motorcycle shows a note: it uses the car road graph.
4. **Preference**: Fastest, Shortest, Least traffic now, Least predicted traffic, or Balanced.
5. **Avoid** (car/motorcycle): toll roads, expressways or ferries (one at a time).
6. **Departure**: *Leave now*, or *Leave at…* and choose a time up to 7 days ahead.
7. Click **Find routes** (usually 2–3 seconds).

## 2. Read the results

* **Recommendation box** — why the top route was chosen and the comparison basis:
  * *Live traffic (TomTom)* — current traffic;
  * *Predicted traffic (TomTom)* — TomTom's prediction for your departure time;
  * *Free-flow estimate (OSRM)* — no traffic data; real times are usually longer
    (a yellow warning says so).
* **Route cards** — ETA, distance, badges:
  * **Recommended**, **Reference** (the default route all others are compared with),
  * **Shortcut** = shorter *and* faster than the reference,
  * **Longcut** = longer *but* faster,
  * **Alternative** = anything else.
  * "vs reference: +1.99 km, +1.4 min" shows the exact differences.
* Click a card (or its line on the map) to see **Why this route**: traffic delay,
  free-flow and typical times, incidents *on* the route, monitored traffic points
  near it, and **Show navigation steps**.
* **Data sources for this result** (bottom) lists every source with its status
  (ok / unavailable / not applicable).

Map layers (checkboxes under the form): **Monitored traffic** (26 sample points,
coloured by congestion), **Incidents**, **Verified shortcuts**.

## 3. Traffic page

Shows the latest observation for each monitored point (slowest first), how old it
is, active incidents, weather by area, and whether Pulse forecasts are enabled
(currently *Off* — no model has passed evaluation). Click a point for its
collected speed history. These are sample points, not city-wide coverage.

## 4. Create an account and sign in

**Sign in** (top right) → *New here? Create an account*. Password: at least 10
characters with upper- and lower-case letters and a digit.

Signed in, you can:

* tick **Save to my trip history** before *Find routes*;
* **My account → Trip history**: view or delete saved trips;
* **Favourites**: save places by label and coordinates;
* **Share a route**: record a trip with GPS or upload a GPX/JSON file and submit
  it. It is map-matched and compared with the standard route. A shortcut becomes
  public only after **3 independent users** confirm it **and** an administrator verifies it;
* **Report incident**: reports stay hidden until an administrator publishes them;
* **Profile**: change name or password, or delete your account and all personal data.

## 5. Administrators

Create the first administrator from the command line
(`docker compose exec backend python -m auth.bootstrap --email … --name …`).
The **Admin** page provides:

* **System health** — database, the three routing servers, TomTom usage today, data freshness;
* **Data freshness** — monitored points fresh/stale, observation counts, provider calls;
* **Moderation** — shortcut candidates (verify / reject / mark stale) and pending incident reports;
* **Models & metrics** — registered models with their measured test errors;
* **Users** — promote/demote or disable accounts (not your own; the last admin is protected);
* **Audit log** — administrative and security actions.

Forecast logging results (prediction vs actual) are available to administrators at
`GET /api/v1/admin/forecast/online` (via http://localhost:8080) or
`http://localhost:8000/v1/admin/forecast/online` with an admin token.

## 6. Mobile app (development build)

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#mobile-app). The mobile app offers
Navigate, Traffic and Account (sign-in, trip history, GPS trip recording,
incident reports) on the same backend.
