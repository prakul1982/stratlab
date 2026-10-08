/* Product analytics (PostHog): which features get used, as a funnel from sign-up to payment.
 *
 * Off until POSTHOG_KEY is in config.js (or VITE_POSTHOG_KEY at build time): with no key nothing is downloaded and
 * nothing is sent. With a key, posthog-js is fetched after the page has drawn, and only if the browser doesn't ask
 * not to be tracked. No session recordings, no autocapture of clicks or inputs, no surveys or remote scripts.
 * People are identified by their internal user id only; event properties pass an allowlist, so an email, a name,
 * a symbol or an amount can't slip in from a call site. Addresses lose their query string and anything that looks
 * like an id or a share token. */

// the slim build: capture and identify only, no recorder, surveys or other add-ons (about a third of the full size)
import type { PostHog } from "posthog-js/dist/module.slim.no-external";

type Value = string | number | boolean | null | undefined;
export type Props = Record<string, Value>;

/** The only properties an event may carry: short words (a region, a plan, where it came from) ... */
const WORDS = new Set(["region", "plan", "period", "focus", "level", "kind", "source", "channel", "method", "tf"]);
/** ... and counts. Never money, prices or quantities. */
const COUNTS = new Set(["count", "filters", "rows", "matched", "results", "stocks"]);
const WORD = /^[a-z][a-z0-9_-]{0,23}$/i;

/** Drop every property that isn't on the allowlist or doesn't look like what it should be. */
export function cleanProps(props?: Props | null): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(props ?? {})) {
    if (WORDS.has(k) && typeof v === "string" && WORD.test(v) && !v.includes("@")) out[k] = v;
    else if (WORDS.has(k) && typeof v === "boolean") out[k] = v;
    else if (COUNTS.has(k) && typeof v === "number" && Number.isInteger(v) && v >= 0 && v < 1e6) out[k] = v;
  }
  return out;
}

/** A page address with nothing personal in it: no query or hash, and ids and share tokens replaced.
 *  Company routes keep their symbol (/research/IN/RELIANCE), which is public information. */
export function maskPath(path: string): string {
  const p = (path || "/").split(/[?#]/)[0] || "/";
  if (/^\/(verdict|v|c)\//.test(p)) return p.replace(/^(\/\w+\/).*$/, "$1:token");
  return p.split("/").map((seg) => (
    /@/.test(seg) ? ":hidden"
      : /^[0-9a-f-]{16,}$/i.test(seg) || (seg.length >= 12 && /\d/.test(seg) && /[a-z]/.test(seg) && !/^[A-Z0-9&_.-]+$/.test(seg)) ? ":id"
        : seg)).join("/");
}

/** A full address the same way: the origin and a masked path; anything else (a referrer from another site) is cut
 *  to its origin. */
function maskUrl(url: unknown): unknown {
  if (typeof url !== "string" || !url) return url;
  try {
    const u = new URL(url);
    return typeof location !== "undefined" && u.origin === location.origin ? u.origin + maskPath(u.pathname) : u.origin;
  } catch { return null; }
}

type Cfg = { key: string; host: string };

/** The key and host from config.js, else from the build; null when analytics is off. */
function analyticsConfig(): Cfg | null {
  const w = typeof window === "undefined" ? undefined : window.STRATLAB_CONFIG;
  let env: Record<string, string | undefined> = {};
  try { env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {}; } catch { /* not built by Vite */ }
  const key = (w?.POSTHOG_KEY || env.VITE_POSTHOG_KEY || "").trim();
  if (!key) return null;
  const host = (w?.POSTHOG_HOST || env.VITE_POSTHOG_HOST || "https://us.i.posthog.com").trim().replace(/\/+$/, "");
  return { key, host };
}

/** Where the owner reads the numbers: the PostHog app for the same region as the host. */
export function analyticsDashboard(): string | null {
  const c = analyticsConfig();
  if (!c) return null;
  return /us\.i\.posthog\.com/.test(c.host) ? "https://us.posthog.com" : /eu\.i\.posthog\.com/.test(c.host) ? "https://eu.posthog.com" : c.host;
}

/** The browser asks not to be tracked (Do Not Track, or Global Privacy Control). */
export function doNotTrack(): boolean {
  if (typeof navigator === "undefined") return false;
  const n = navigator as Navigator & { msDoNotTrack?: string; globalPrivacyControl?: boolean };
  const w = typeof window === "undefined" ? undefined : (window as Window & { doNotTrack?: string });
  return [n.doNotTrack, n.msDoNotTrack, w?.doNotTrack].some((v) => v === "1" || v === "yes") || n.globalPrivacyControl === true;
}

/* ---------- the client, loaded once on demand ---------- */
let ph: PostHog | null = null;
let loading: Promise<PostHog | null> | null = null;
const queue: ((p: PostHog) => void)[] = [];
let context: { backtests?: number; newAccount?: boolean } = {};

/** Strip anything address-shaped down to its masked form, on every event (the library's own ones included). */
function scrub<T extends { properties?: Record<string, unknown>; $set?: Record<string, unknown>; $set_once?: Record<string, unknown> } | null>(ev: T): T {
  if (!ev) return ev;
  for (const bag of [ev.properties, ev.$set, ev.$set_once]) {
    if (!bag) continue;
    for (const k of Object.keys(bag)) {
      if (/_url$|referrer$/.test(k)) bag[k] = maskUrl(bag[k]);
      else if (/pathname$/.test(k)) bag[k] = typeof bag[k] === "string" ? maskPath(bag[k] as string) : bag[k];
      else if (/^\$?title$|email|^\$?name$/i.test(k)) delete bag[k];
    }
  }
  return ev;
}

function load(): Promise<PostHog | null> {
  const cfg = analyticsConfig();
  if (!cfg || doNotTrack()) return Promise.resolve(null);
  loading ??= new Promise<void>((ok) => {
    // after the first paint, when the browser is idle: analytics never slows the page down
    const idle = (window as Window & { requestIdleCallback?: (f: () => void, o?: { timeout: number }) => void }).requestIdleCallback;
    if (idle) idle(() => ok(), { timeout: 3000 }); else setTimeout(ok, 1500);
  }).then(() => import("posthog-js/dist/module.slim.no-external")).then(({ default: posthog }) => {
    posthog.init(cfg.key, {
      api_host: cfg.host,
      autocapture: false, capture_pageview: false, capture_pageleave: false, rageclick: false,
      capture_dead_clicks: false, capture_heatmaps: false, capture_exceptions: false, capture_performance: false,
      disable_session_recording: true, disable_surveys: true, disable_web_experiments: true,
      disable_product_tours: true, disable_conversations: true,
      disable_external_dependency_loading: true, advanced_disable_flags: true,
      disable_compression: true,          // plain JSON, so what is sent can be read in the browser's network panel
      respect_dnt: true, mask_personal_data_properties: true, mask_all_text: true, mask_all_element_attributes: true,
      person_profiles: "identified_only", persistence: "localStorage",
      before_send: (ev) => scrub(ev),
    });
    ph = posthog;
    queue.splice(0).forEach((f) => { try { f(posthog); } catch { /* one bad call doesn't stop the rest */ } });
    return posthog;
  }).catch(() => null);
  return loading ?? Promise.resolve(null);
}

/** Run something on the client once it's loaded; nothing at all when analytics is off. */
function withClient(f: (p: PostHog) => void) {
  try {
    if (ph) { f(ph); return; }
    if (!analyticsConfig() || doNotTrack()) return;
    if (queue.length < 100) queue.push(f);
    void load();
  } catch { /* analytics never breaks the app */ }
}

/** Record a product event: `track("backtest run", { region: "IN" })`. Never throws, and does nothing without a key. */
export function track(event: string, props?: Props | null) {
  const clean = cleanProps(props);
  withClient((p) => p.capture(event, clean));
}

/** A page was opened (called on every route change). */
export function pageview(path: string) {
  const masked = maskPath(path);
  withClient((p) => p.capture("$pageview", { $current_url: location.origin + masked, $pathname: masked }));
}

/** Tie this browser's events to the signed-in account, by its internal id only. The plan rides along on every event.
 *  `backtests` (this month) and `createdAt` stay in this file, to tell a first backtest from the rest. */
export function identify(userId: string, o: { plan?: string | null; backtests?: number; createdAt?: string | null } = {}) {
  if (!userId) return;
  const age = o.createdAt ? Date.now() - new Date(o.createdAt).getTime() : NaN;
  context = { backtests: o.backtests, newAccount: age < 31 * 86_400_000 };
  withClient((p) => {
    if (p.get_distinct_id() !== userId) p.identify(userId);
    if (o.plan && WORD.test(o.plan)) p.register({ plan: o.plan });
  });
}

/** Signed out: forget the account, so the next person on this browser starts fresh. */
export function resetAnalytics() {
  context = {};
  if (ph) { try { ph.reset(); } catch { /* ignore */ } }
}

/** A backtest finished: also "first backtest run" when it's the account's first one this month on a new account. */
export function trackBacktest(source: string) {
  if (context.newAccount && context.backtests === 0) track("first backtest run", { source });
  if (typeof context.backtests === "number") context.backtests += 1;
  track("backtest run", { source });
}

/** Signed in for the first time a few minutes after the account was made: a sign-up. Sent once per browser. */
export function trackSignup(userId: string, createdAt?: string | null) {
  if (!createdAt || Date.now() - new Date(createdAt).getTime() > 15 * 60_000) return;
  const key = "stratlab.signedup";
  try { if (localStorage.getItem(key) === userId) return; localStorage.setItem(key, userId); } catch { /* storage off */ }
  track("signed up");
}
