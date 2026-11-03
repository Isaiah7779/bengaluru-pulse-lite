# User guide

Open the web app at **http://localhost:8080** (after `docker compose up -d`).
Every page starts behind the sign-in screen: you need an account to plan routes
or view traffic (see [§4](#4-create-an-account-and-sign-in)). Once you are signed in,
the side bar has **Home**, **Navigate**, **Traffic**, **Insights**, **Journal**,
**About**, **My account** and, for administrators only, **Admin**.

## 1. Plan a route (sign-in required)

Sign in first (§4). The API refuses route requests without a signed-in account
(`API_AUTH_REQUIRED=true`, the default in `docker-compose.yml` and `render.yaml`).

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
   Shown only when the routing servers support it; the free-tier deployment uses
   public OSRM servers that do not, so the option is hidden there
   ([DEPLOY_FREE_TIER.md](DEPLOY_FREE_TIER.md#free-tier-limits-you-will-notice)).
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

The sign-in screen appears whenever you are signed out. Choose *New here? Create an
account*. Password: at least 10 characters with upper- and lower-case letters and a
digit.

How sign-in works depends on how the server is configured
([AUTHENTICATION.md](AUTHENTICATION.md)):

* **Firebase sign-in** (when the server has `FIREBASE_PROJECT_ID` set): e-mail and
  password or *Continue with Google*. You must verify your e-mail address before the
  app lets you in; *Forgot password?* sends a reset link.
* **Built-in accounts** (no Firebase configured, `LEGACY_AUTH_ENABLED=true`): e-mail
  and password only. There is no e-mail verification and no password reset.

Signed in, you can plan routes and view traffic (§1–§3), and also:

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

## 6. On phones, tablets and other computers

**Any device with a modern browser** (Android, iPhone, iPad, Windows, macOS, Linux):
open the address the system owner gives you, either the same-Wi-Fi address
(e.g. `http://192.168.1.7:8080`) or the HTTPS address. The layout adapts to phone,
tablet and desktop screens. On a phone you can add it to the home screen:
Safari → Share → *Add to Home Screen*, or Chrome → ⋮ → *Add to Home screen*.

**Android app (APK)**: install the provided `.apk` (you may need to allow installing apps
from your browser or file manager). The app opens on its sign-in screen, which also has
the **Server** setting (later under **Account → Server**). Enter the HTTPS address
you were given (for example `https://<name>.trycloudflare.com`), tap **Test and save**,
then sign in. The app offers Navigate, Traffic and Account (sign-in, trip history, GPS trip recording,
incident reports) on the same backend as the website.

**iPhone/iPad app**: not yet installable. App Store Expo Go does not support SDK 58 yet,
and a signed iOS build needs a paid Apple Developer account. Use the website in Safari,
which works on the iPhone. Details: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#9-mobile-app).
