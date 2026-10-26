# Authentication and personal data (Firebase)

Bengaluru Pulse uses **Firebase Authentication** for identity, **Cloud Firestore** for a
user's own favourites, journal and preferences, and keeps everything else (trips, routes,
incidents, community submissions, roles, admin records) in **PostgreSQL/PostGIS**.

| Concern | Where | Notes |
|---|---|---|
| Identity, sign-in, e-mail verification, password reset, Google | Firebase Authentication | Same project for web and Android |
| Role (`user` / `admin`), account status | PostgreSQL `users` | Never taken from a token or from Firestore |
| Saved trips, submissions, incident reports | PostgreSQL | Unchanged; owner-filtered by the API |
| Favourites, journal, preferences | Firestore `users/{uid}/…` | Owner-only security rules |

No PostgreSQL data was migrated. The built-in (pre-Firebase) sign-in keeps working while
`LEGACY_AUTH_ENABLED=true`, so nothing breaks before Firebase is configured.

## 1. How it works

**Backend (FastAPI).** Every request carries `Authorization: Bearer <token>`.

* *Firebase ID tokens* are verified by the official **Firebase Admin SDK**
  (`firebase_admin.auth.verify_id_token`). It checks the RS256 signature against
  Google's published keys, the issuer `https://securetoken.google.com/<project>`, the
  audience (project ID), the expiry and issue time, and the subject (UID). The backend
  needs only `FIREBASE_PROJECT_ID`, so **no service-account key** is required.
* The token's e-mail must be **verified** (`email_verified=true`); otherwise the
  backend answers `403 email_not_verified`. This applies to Google too: Google sign-in
  counts only when Firebase reports the address as verified.
* The account row is found by **Firebase UID only**. A first sign-in creates a row with
  role `user`. Registration and Google sign-in can never create an admin.
* *Legacy tokens* (HS256, issued by `/v1/auth/login`) are accepted only while
  `LEGACY_AUTH_ENABLED=true`.
* The role is always re-read from PostgreSQL. Disabling a user
  (`is_active=false`, Admin page) locks them out on the next request.

**Endpoint classes** (see `backend/main.py`):

| Class | Endpoints | Guard |
|---|---|---|
| Public operational | `GET /health`, `GET /health/ready` | none (container health check, uptime) |
| Sign-in | `/v1/auth/*` | each endpoint enforces its own rule (password, Firebase token, or a signed-in user) |
| Admin only | `/v1/admin/*` | `require_admin` (role from DB) |
| Signed-in user | `/v1/me/*`, `/v1/routes`, `/v1/vehicles`, `/v1/geocode/*`, `/v1/traffic/*`, `/v1/weather/*`, `/v1/incidents*`, `/v1/forecast/*`, `/v1/community/*`, legacy V1 routes | `app_access` when `API_AUTH_REQUIRED=true` |
| Internal service | none over HTTP | the collector writes to PostgreSQL directly; health checks use `/health` |

Per-user records (`/v1/me/trips`, favourites, submissions, reports) are always filtered
by the caller's user ID; another user's ID gives `404`.

**Existing accounts: linking without takeover.** If a verified Firebase user's e-mail
matches an existing built-in account, the backend does **not** merge them. It answers
`409 account_link_required`, and the app asks for that account's **old password**
(`POST /v1/auth/link`, rate-limited). Only then is the Firebase UID attached. The
account keeps its ID, role, trips and records, and adopts the verified Firebase e-mail
when that address is free. An e-mail match alone never transfers an account.

The two accounts in the current local database use reserved test domains
(`*.test` / `example.*`). Nobody can verify those in Firebase, so they can only be
linked with their old passwords.

**Web app.** Every page is behind the sign-in screen (sign in, create account, Google,
forgot password). The hash route is preserved, so the user lands on the page they asked
for. Unverified accounts see *Verify your e-mail* with **Resend** and **I've verified —
continue**. Fresh ID tokens are attached by the SDK and refreshed once automatically if
the server reports `token_expired`. Passwords are never stored in the browser or in
Firestore.

**Android app.** It has the same flows. The session is kept in `expo-secure-store`
(Android Keystore). Google sign-in uses the native Credential/Google Sign-In flow
(`@react-native-google-signin/google-signin`); its ID token is exchanged with
`GoogleAuthProvider.credential`. There is no browser popup and no `google-services.json`.

**Account deletion** is explicit. It needs a confirmation dialog and a fresh sign-in.
It then removes the Firestore documents, then the PostgreSQL account and records
(trips, favourites, submissions), then the Firebase user. The backend refuses Firebase
deletions without `confirm: true` and a sign-in from the last five minutes.

## 2. Firestore data and rules

```
users/{uid}/favorites/{favoriteId}  { label, detail?, lat, lon, kind?, createdAt, updatedAt }
users/{uid}/journal/{entryId}       { title, body, mood?, tripId?, createdAt, updatedAt }
users/{uid}/preferences/app         { vehicle?, routePreference?, avoid?, departure?, updatedAt }
```

`firebase/firestore.rules`:

* Only the signed-in owner with a verified e-mail can read or write. Everything else is
  denied: no profile document, no role fields, no other collections.
* Each field is checked for allowed keys, type, length, enum values and coordinates
  inside the Bengaluru bounds.
* Timestamps must be server timestamps, and `createdAt` is immutable.

Rules tests run on the local emulator:

```bash
cd firebase
npm install
npm run test:rules
```

The emulator needs Java. firebase-tools 13.35.1 works with JDK 17.

## 3. Firebase console setup (manual, free Spark plan)

Stay on the free **Spark** plan; nothing here needs Blaze or billing.

1. **Create a project** at <https://console.firebase.google.com>, for example
   `bengaluru-pulse`. Google Analytics is not needed.
2. **Authentication → Sign-in method:**
   * Enable **Email/Password**. Leave "Email link" off.
   * Enable **Google**: pick a support e-mail and save. Firebase creates a *Web client*
     OAuth ID. You can find it under **Google → Web SDK configuration**, or in Google
     Cloud console → **APIs & Services → Credentials** ("Web client (auto created by
     Google Service)").
   * Recommended: **Settings → Password policy**: minimum length 10, require upper case,
     lower case and a number. The apps enforce the same rule.
   * Optional: **Templates** → customise the verification and reset e-mails.
3. **Authentication → Settings → Authorized domains:** `localhost` is present by default.
   * Add the domain you serve the web app from.
   * A **Cloudflare quick tunnel** (`*.trycloudflare.com`) gets a **new random hostname
     every time it starts**. Add the current one for testing and replace it when it
     changes. Never put it in the code.
   * Before production Google sign-in, use a **stable domain** (your own domain or a
     named Cloudflare tunnel) and add it here.
   * A LAN address such as `http://192.168.1.7:8080` is not a valid authorized domain.
     E-mail sign-in may still work there, but Google sign-in on the web will not.
4. **Project settings → Your apps → Web app** (`</>`). Register "Bengaluru Pulse web".
   Copy `apiKey`, `authDomain`, `projectId` and `appId`. These are public client
   identifiers.
5. **Project settings → Your apps → Android app.**
   * Package name: `org.bengalurupulse.app` (verified in `mobile/app.json`).
   * Add **both** SHA fingerprints of the release upload key:
     * SHA-1: `41:1B:2F:45:0E:AE:56:F1:0A:AC:3E:8A:7E:95:CC:D5:75:50:B7:3A`
     * SHA-256: `9C:BF:65:66:FA:F0:A3:E9:DC:FD:49:97:8F:57:82:EA:2A:CE:DF:D7:B8:FD:12:95:98:37:38:6E:E8:E6:F8:A1`
   * Optionally also add the debug key fingerprint for `npx expo run:android` builds:
     `keytool -list -v -keystore mobile/android/app/debug.keystore -storepass android`.
   * Adding the SHA-1 lets Firebase create the **Android OAuth client** that native
     Google sign-in requires.
   * The `google-services.json` download is **not needed** (the app uses the JS SDK). If
     you download it anyway, keep it out of Git (it is in `.gitignore`).
   * If the app is later distributed through Google Play, also add Play's **app signing
     key** SHA-1/SHA-256 (Play Console → App integrity).
6. **Firestore Database → Create database.** Choose **production mode**, never test mode,
   and a nearby region such as `asia-south1` (the location is permanent). Then deploy the
   rules:

   ```bash
   cd firebase
   npx firebase login          # opens your browser; your own Google account
   npx firebase use --add      # choose the project, alias "prod"
   npm run deploy:rules        # firestore:rules only
   ```

   Or paste `firebase/firestore.rules` into **Firestore → Rules** and publish.
7. **iOS (later, needs a Mac and an Apple Developer account).** Register an iOS app
   (`org.bengalurupulse.app`) and set `GOOGLE_IOS_URL_SCHEME` to its reversed client ID
   when building.

## 4. Configuration

Nothing secret is needed for Firebase on the server. The web and Android values are
public identifiers. Put them in local files that Git ignores, never in chat or commits.

**Docker / production** (root `.env`, git-ignored; see `.env.example`):

```
FIREBASE_PROJECT_ID=<project-id>
FIREBASE_AUTH_DOMAIN=<project-id>.firebaseapp.com
FIREBASE_WEB_API_KEY=<web apiKey>
FIREBASE_WEB_APP_ID=<web appId>
API_AUTH_REQUIRED=true
LEGACY_AUTH_ENABLED=true          # switch to false after existing accounts are linked
LEGACY_REGISTRATION_ENABLED=true  # set false as soon as Firebase sign-in works
```

Then rebuild only what changed:

```bash
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
```

The backend applies migration `0003` on start. It adds a nullable `users.firebase_uid`
and allows `password_hash` to be NULL, so no data changes.

**Web development:** `frontend/.env.local` with `REACT_APP_FIREBASE_*`.

**Android:** `mobile/.env.local` with `EXPO_PUBLIC_FIREBASE_*` and
`EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` (the Web client ID from step 2). Expo inlines
`EXPO_PUBLIC_*` at build time.

**Administrator.** Roles are only granted on the server:

* Link the existing admin account with its old password, **or**
* sign up with Firebase and promote the account:

  ```bash
  docker compose exec backend python -m auth.bootstrap --email <you@domain> --promote --force
  ```

  `--force` is needed because an admin already exists. It is audit-logged.

## 5. Android release signing

The Android release (upload) key was created locally:

* Keystore: `%USERPROFILE%\.bengaluru-pulse-keys\bengaluru-pulse-upload.jks` (PKCS12,
  RSA 4096, alias `bengaluru-pulse-upload`, valid until 2054). It is outside the
  repository and outside OneDrive.
* Its password is in `%USERPROFILE%\.gradle\gradle.properties` (`PULSE_UPLOAD_*`).
  This is user-level and never committed.
* **Back up both** the `.jks` and the password, offline or in a password manager. If you
  lose them, you cannot sign updates for installs that used this key.
* `mobile/plugins/withReleaseSigning.js` makes release builds use this key when the
  properties exist. Otherwise it keeps the template debug key, which is what earlier APKs
  used.

To build:

```bash
cd mobile
npx expo prebuild --platform android --no-install
cd android
./gradlew assembleRelease -PreactNativeArchitectures=armeabi-v7a,arm64-v8a
apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
```

An APK signed with the new key **cannot update** an installed APK signed with the old
debug key. Uninstall the old app first.

## 6. Testing

| Check | How |
|---|---|
| Token verification, mandatory access, linking, isolation, deletion | `backend/tests/test_firebase_auth.py`: real RS256 tokens through the Admin SDK, with only the certificate download replaced |
| Firestore rules | `cd firebase && npm run test:rules` (emulator) |
| Web flows (gate, verification, linking, token refresh) | `cd frontend && npm test` |
| End to end without a real project | Run `npm run emulators` in `firebase/`. Start the backend with `FIREBASE_PROJECT_ID=demo-bengaluru-pulse FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099` (never in production; refused when `ENVIRONMENT=production`). Start the web app with `REACT_APP_FIREBASE_EMULATOR=true REACT_APP_FIREBASE_API_KEY=demo REACT_APP_FIREBASE_PROJECT_ID=demo-bengaluru-pulse`. Verification links are listed at `http://127.0.0.1:9099/emulator/v1/projects/demo-bengaluru-pulse/oobCodes`. |

**After configuring the real project:**

1. Register a new account and check that you get the verification screen.
2. Open the link in the e-mail, press **I've verified**, and check that the app opens.
3. Sign out, sign back in, and check that your favourites and preferences remain.
4. Use **Forgot password** and check that the e-mail arrives.
5. Use **Continue with Google** on an authorized domain.
6. Check that a normal account has no Admin link and that `/api/v1/admin/users` returns 403.
7. Link the old admin account with its old password and check that Admin appears.
8. On Android: install the new APK, use **Continue with Google**, close and reopen the
   app, and check that you are still signed in.
