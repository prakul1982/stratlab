/* The Meta Pixel and Microsoft Clarity (ADS-1). Nothing here runs until components/Tracking.tsx calls it, which it does only for a
 * visitor who chose "Allow", on a page lib/ads.ts's trackersFor allows, and with the ID set. The scripts are fetched here and nowhere
 * else (index.html names neither). Facts about what is sent are in the Privacy page.
 *
 * Meta Pixel: PageView on each page the visitor opens, and CompleteRegistration once when a sign-up completes. Nothing else:
 * the pixel's automatic extras (button clicks, page metadata, history changes) are switched off, so no event but those two
 * is sent, and none from the private pages. Clarity: recorded with every word masked (data-clarity-mask on the page's root, the
 * same as the project's "Strict" masking); stopped on a private page. */

type Fbq = ((...a: unknown[]) => void) & { callMethod?: (...a: unknown[]) => void; queue: unknown[][]; loaded: boolean; version: string; push: unknown; disablePushState?: boolean };
type W = Window & { fbq?: Fbq; _fbq?: Fbq; clarity?: ((...a: unknown[]) => void) & { q?: unknown[][] } };

let pixelId = "";
let lastView = "";
let clarityId = "";
let clarityOn = false;
let pendingSignup = false;
const signupListeners = new Set<() => void>();

/** The pixel's script (once) with its automatic extras off, then the ID. */
export function loadPixel(id: string): void {
  const w = window as W;
  if (pixelId) return;
  pixelId = id;
  if (!w.fbq) {
    const n = function (...a: unknown[]) { if (n.callMethod) n.callMethod(...a); else n.queue.push(a); } as Fbq;
    w.fbq = n; w._fbq = n;
    n.push = n; n.loaded = true; n.version = "2.0"; n.queue = [];
    const s = document.createElement("script");
    s.async = true;
    s.src = "https://connect.facebook.net/en_US/fbevents.js";
    document.head.appendChild(s);
  }
  w.fbq.disablePushState = true;                   // a page change is counted below, by the app's own router, only where allowed
  w.fbq("set", "autoConfig", false, id);           // no automatic button-click or page-metadata events
  w.fbq("init", id);
}

/** One PageView for a page address (the same address twice in a row counts once). */
export function pixelPageView(path: string): void {
  const w = window as W;
  if (!pixelId || !w.fbq || path === lastView) return;
  lastView = path;
  w.fbq("track", "PageView");
}

/** A sign-up completed (lib/analytics trackSignup calls this). Sent once the pixel is loaded; never if it isn't. */
export function markSignup(): void { pendingSignup = true; signupListeners.forEach((fn) => fn()); }
export function onSignup(fn: () => void): () => void { signupListeners.add(fn); return () => { signupListeners.delete(fn); }; }
export function flushSignup(): void {
  const w = window as W;
  if (!pendingSignup || !pixelId || !w.fbq) return;
  pendingSignup = false;
  w.fbq("track", "CompleteRegistration");
}

/** Clarity, with every word masked. Started again if it was stopped on a private page. */
export function startClarity(id: string): void {
  const w = window as W;
  if (clarityOn) return;
  clarityOn = true;
  // strict masking from the first frame: all text and inputs are hidden in the recording (the project's setting says the same)
  document.getElementById("root")?.setAttribute("data-clarity-mask", "True");
  document.body?.setAttribute("data-clarity-mask", "True");
  if (clarityId) { w.clarity?.("start"); return; }
  clarityId = id;
  const c = w.clarity ?? function (...a: unknown[]) { (c.q = c.q || []).push(a); } as NonNullable<W["clarity"]>;
  w.clarity = c;
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.clarity.ms/tag/${encodeURIComponent(id)}`;
  document.head.appendChild(s);
}

/** On a private page: Clarity stops recording (only if it was started). */
export function stopClarity(): void {
  if (!clarityOn) return;
  clarityOn = false;
  try { (window as W).clarity?.("stop"); } catch { /* the script is blocked */ }
}
