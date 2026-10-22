# Security

## Authentication

* Passwords: bcrypt (cost 12); policy ≥ 10 chars, upper + lower case, digit, ≤ 72 bytes.
  Admin bootstrap requires ≥ 14 chars.
* Sessions: HS256 JWT bearer tokens (60 min) with `jti`, `iat`, `exp`, issuer.
  Logout stores the `jti` in `revoked_tokens`; revoked/expired/forged tokens → 401.
* Production refuses to start without `JWT_SECRET` (≥ 32 chars) or with wildcard CORS.
* Login: generic "incorrect e-mail or password"; a dummy bcrypt check equalises timing
  for unknown e-mails; sliding-window rate limit (5 failures / 5 min per e-mail and per IP → 429).
* Tokens are sent as `Authorization: Bearer` (not cookies), so CSRF does not apply;
  CORS `allow_credentials=False`, explicit origins only.

## Authorization (enforced in the backend)

The role is **read from the database on every request**, never from token claims,
so demotion or deactivation takes effect immediately (tested).

| Capability | Anonymous | User | Admin |
|---|---|---|---|
| Plan routes, search places, view traffic/incidents/weather, view verified shortcuts | ✓ | ✓ | ✓ |
| Save trips, favourites, own trip history | – | own only | own only |
| Submit community routes / incident reports | – | ✓ (rate-limited) | ✓ |
| Moderate submissions and incident reports | – | – | ✓ |
| Manage users (role, active) | – | – | ✓ (not self; never the last admin) |
| Data freshness, model metrics, system health, audit log | – | – | ✓ |

* No self-promotion: registration and profile schemas have no role/active fields;
  extra fields are ignored (tested). Admins cannot change their own role or status;
  the last active admin cannot be demoted, disabled or self-deleted.
* No IDOR: personal queries filter by `user_id = caller`; other users' ids return 404.
* Shortcuts are never auto-verified: verification requires state `under_review`
  (≥ 3 independent users + consistency checks) **and** an admin decision.
* Initial admin: `python -m auth.bootstrap --email … ` reads the password from
  `BOOTSTRAP_ADMIN_PASSWORD` or an interactive prompt (never a CLI argument);
  refuses if an admin exists unless `--force`; audited.

## Secrets

* All secrets via environment (`SecretStr` in settings; never in repr/logs).
  `.env` files are gitignored; `git ls-files` shows no secret files.
* **Key-leak fix:** V1 returned `requests` exception text, which contains the full
  URL including `?key=<TomTom key>`, to API clients. Now provider errors carry only
  safe messages; a logging filter redacts `key=`, `token=`, bearer headers and
  password fields from every log record and traceback; `httpx` URL logging is
  silenced. Verified by tests and live: a run with an invalid key logged it 0 times.
* Local development credentials (dev admin and test user) exist only as comments in
  the gitignored `backend/.env`.

## Transport and headers

* Production: Caddy with automatic HTTPS, HSTS, `nosniff`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy` limiting geolocation to self. Only ports 80/443 are published;
  Postgres, OSRM, backend and frontend are internal to the Docker network.
* API adds `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY`, request ids.

## Input handling and abuse limits

* Pydantic validation on every body/query; bounded sizes (traces ≤ 5,000 points,
  notes ≤ 500 chars, queries ≤ 120 chars, ≤ 1 avoid option, departures ≤ 7 days ahead).
* Per-user limits: 20 route submissions/day, 10 incident reports/hour, 50 favourites.
* SQL via the ORM / bound parameters only.
* The mobile map loads Leaflet with Subresource Integrity hashes (verified against npm).
* Mobile tokens are stored in the OS keystore (expo-secure-store); the web stores the
  token in `localStorage` (XSS risk mitigated by React escaping and no `dangerouslySetInnerHTML`).

## Known gaps (not implemented)

* No e-mail verification or password-reset flow (needs an e-mail provider).
* No refresh tokens; users sign in again after 60 minutes.
* The login rate limiter is in-process; behind several API replicas it should move to the database/Redis.
* No CSP header yet on the web app (Leaflet tiles and inline styles need a tuned policy).
* Dependency vulnerability scanning is not part of CI yet (`npm audit`/`pip-audit` recommended).
