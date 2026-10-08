import { CFG } from "./config";

/** Error alerts: only when a Sentry DSN is in config.js, and the SDK is only downloaded then. */
export function startErrorReports() {
  if (!CFG.SENTRY_DSN) return;
  import("@sentry/browser").then((S) => S.init({ dsn: CFG.SENTRY_DSN, environment: location.hostname,
    // nothing personal: no user fields, cookies, headers, bodies or query strings
    dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false },
    ignoreErrors: ["ResizeObserver loop", "AbortError", "Failed to fetch", "Load failed", "NetworkError"] })).catch(() => {});
}
