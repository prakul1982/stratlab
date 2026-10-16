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

const NOISE = /ResizeObserver loop|AbortError|Failed to fetch|Load failed|NetworkError|dynamically imported module|importing a module script|loading chunk/i;

/** A crash, to PostHog's error tracking (lib/analytics, loaded only when something breaks; nothing without its key).
 *  Dropped connections and failed downloads aren't the page's bugs and are left out. */
export function reportCrash(err: unknown, how: "window" | "promise" | "page") {
  if (NOISE.test(`${(err as Error)?.name ?? ""} ${(err as Error)?.message ?? err}`)) return;
  void import("./analytics").then((a) => a.trackError(err, how)).catch(() => undefined);
}

let listening = false;

/** Crashes in the browser go to PostHog whether or not Sentry is set up. */
function listen() {
  if (listening) return;
  listening = true;
  window.addEventListener("error", (e) => { if (e.error) reportCrash(e.error, "window"); });    // a script error, not a failed image
  window.addEventListener("unhandledrejection", (e) => reportCrash(e.reason, "promise"));
}

/** Error alerts: only when a Sentry DSN is in config.js, and the SDK is only downloaded then. With `lazy` (a visitor's
 * page: the policies, the library), it isn't downloaded at all until something actually goes wrong, so a page of
 * text doesn't carry the error reporter's weight (R6V-018); the error that woke it is reported once it has loaded. */
export function startErrorReports({ lazy = false }: { lazy?: boolean } = {}) {
  listen();
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
