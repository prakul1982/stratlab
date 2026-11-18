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

type How = "window" | "promise" | "page";
declare global { interface Window { __stratlabCrash?: (err: unknown, how: How) => void; __stratlabCrashes?: [unknown, How][] } }

/** A crash, to PostHog's error tracking. lib/analytics takes it once it has loaded (it sets window.__stratlabCrash);
 *  until then up to 10 wait in window.__stratlabCrashes. Nothing is imported from here, so no page downloads a file
 *  more for it. Dropped connections and failed downloads aren't the page's bugs and are left out. */
export function reportCrash(err: unknown, how: How) {
  if (NOISE.test(`${(err as Error)?.name ?? ""} ${(err as Error)?.message ?? err}`)) return;
  if (window.__stratlabCrash) { window.__stratlabCrash(err, how); return; }
  const waiting = (window.__stratlabCrashes ??= []);
  if (waiting.length < 10) waiting.push([err, how]);
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
/** LIVE12A-002: without `lazy` (a signed-in app), the SDK (about 140 kB compressed) is downloaded once the first page has drawn and the
 * browser is idle, not beside the app's own code on the first load, where it slowed the first app page of a session; an error before
 * then wakes it at once and is reported, as with `lazy`. */
export const SENTRY_AFTER_MS = 4000;

export function startErrorReports({ lazy = false }: { lazy?: boolean } = {}) {
  listen();
  if (!CFG.SENTRY_DSN) return;
  const off = () => {
    window.removeEventListener("error", onError);
    window.removeEventListener("unhandledrejection", onRejection);
  };
  const first = (err: unknown) => {
    off();
    void load().then((S) => { if (S && err) S.captureException(err); });
  };
  const onError = (e: ErrorEvent) => { if (e.error) first(e.error); };                 // a script error, not a failed image
  const onRejection = (e: PromiseRejectionEvent) => first(e.reason);
  window.addEventListener("error", onError);
  window.addEventListener("unhandledrejection", onRejection);
  if (lazy) return;
  // once loaded, the SDK's own handlers report errors: the early ones above stop, so nothing is reported twice
  const now = () => { off(); void load(); };
  const later = () => { const w = window as Window & { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => number };
    if (w.requestIdleCallback) w.requestIdleCallback(now, { timeout: SENTRY_AFTER_MS }); else now(); };
  if (document.readyState === "complete") window.setTimeout(later, SENTRY_AFTER_MS);
  else window.addEventListener("load", () => window.setTimeout(later, SENTRY_AFTER_MS), { once: true });
}
