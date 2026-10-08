import { CFG } from "./config";

type Sentry = typeof import("@sentry/browser");
let loading: Promise<Sentry | null> | null = null;

/** Download the SDK and start it (once). */
function load(): Promise<Sentry | null> {
  loading ??= import("@sentry/browser").then((S) => {
    S.init({ dsn: CFG.SENTRY_DSN, environment: location.hostname,
      // nothing personal: no user fields, cookies, headers, bodies or query strings
      dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [], urlQueryParams: false },
      ignoreErrors: ["ResizeObserver loop", "AbortError", "Failed to fetch", "Load failed", "NetworkError"] });
    return S;
  }).catch(() => null);
  return loading;
}

/** Error alerts: only when a Sentry DSN is in config.js, and the SDK is only downloaded then. With `lazy` (a visitor's
 * page: the policies, the library), it isn't downloaded at all until something actually goes wrong, so a page of
 * text doesn't carry the error reporter's weight (R6V-018); the error that woke it is reported once it has loaded. */
export function startErrorReports({ lazy = false }: { lazy?: boolean } = {}) {
  if (!CFG.SENTRY_DSN) return;
  if (!lazy) { void load(); return; }
  const first = (err: unknown) => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
    void load().then((S) => { if (S && err) S.captureException(err); });
  };
  const onError = (e: ErrorEvent) => { if (e.error) first(e.error); };                 // a script error, not a failed image
  const onRejection = (e: PromiseRejectionEvent) => first(e.reason);
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
}
