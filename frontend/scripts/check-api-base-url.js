#!/usr/bin/env node
// Build guard for hosted builds (Vercel buildCommand). CRA bakes REACT_APP_API_BASE_URL in at
// build time; without it the app falls back to same-origin "/api", which a static host answers
// with 404/405. Fail the build instead, and say which Vercel environment lacked the variable so
// the fix (scope, branch, name) is visible in the build log. Prints the URL's origin only.
const env = process.env;
const raw = env.REACT_APP_API_BASE_URL;
const context = [
  `VERCEL_ENV=${env.VERCEL_ENV || "(unset)"}`,
  `VERCEL_TARGET_ENV=${env.VERCEL_TARGET_ENV || "(unset)"}`,
  `branch=${env.VERCEL_GIT_COMMIT_REF || "(unset)"}`,
].join(" ");

function fail(message) {
  console.error(`[check-api-base-url] ${message}`);
  console.error(`[check-api-base-url] build context: ${context}`);
  const names = Object.keys(env).filter((k) => /API_BASE_URL/i.test(k) && k !== "REACT_APP_API_BASE_URL");
  if (names.length) {
    console.error(`[check-api-base-url] similar variables present (not read by this CRA app): ${names.join(", ")}`);
  }
  console.error(
    "[check-api-base-url] Add REACT_APP_API_BASE_URL in Vercel > Project > Settings > Environment Variables " +
      "for this environment (and branch, for Preview), then redeploy. Example: https://<your-api>.onrender.com"
  );
  process.exit(1);
}

if (!raw || !raw.trim()) fail("REACT_APP_API_BASE_URL is not set for this build.");

let url;
try {
  url = new URL(raw.trim());
} catch {
  fail("REACT_APP_API_BASE_URL is not a valid absolute URL.");
}
if (!/^https?:$/.test(url.protocol)) fail("REACT_APP_API_BASE_URL must start with http:// or https://.");

console.log(`[check-api-base-url] OK: API origin ${url.origin} (${context})`);
