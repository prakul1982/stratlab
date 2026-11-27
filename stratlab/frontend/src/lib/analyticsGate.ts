/* Whether this browser's visits are left out of usage analytics, before anything is loaded or sent (conv101, T2). Off when:
 *  - the browser asks not to be tracked (Do Not Track or Global Privacy Control);
 *  - it is an automated or headless browser (a test run, a crawler, a speed checker): navigator.webdriver, or a user agent that names one;
 *  - the device is marked internal: the owner opens any StratLab page once with ?internal=1 on each of his devices (?internal=0 undoes it).
 *    The mark is one localStorage entry, stratlab.internal; public/pv.js (the pages the server draws) reads and sets the same entry;
 *  - the signed-in account is one of StratLab's own (an admin or a test account): the server says so on /me (`internal`), never a list of
 *    addresses in this code. Such an account marks the device internal too, so its signed-out visits on that device are left out as well.
 * Small and dependency-free: the landing page, the app and lib/api.ts all read it. */

export const INTERNAL_KEY = "stratlab.internal";

let accountInternal = false;
let memoryMark: boolean | null = null;          // storage off: the mark for this page view only

/** The browser asks not to be tracked (Do Not Track, or Global Privacy Control). */
export function doNotTrack(): boolean {
  if (typeof navigator === "undefined") return false;
  const n = navigator as Navigator & { msDoNotTrack?: string; globalPrivacyControl?: boolean };
  const w = typeof window === "undefined" ? undefined : (window as Window & { doNotTrack?: string });
  return [n.doNotTrack, n.msDoNotTrack, w?.doNotTrack].some((v) => v === "1" || v === "yes") || n.globalPrivacyControl === true;
}

/** A user agent that names an automated, headless or crawling browser (the same words as public/pv.js). */
export const AUTOMATED_UA = /HeadlessChrome|PhantomJS|Puppeteer|Playwright|Selenium|Cypress|Lighthouse|PTST|GTmetrix|PageSpeed|bot[\/;)-]|crawler|spider|slurp|facebookexternalhit/i;

/** An automated or headless browser: navigator.webdriver, its user agent, or its client hints naming HeadlessChrome. */
export function automated(): boolean {
  if (typeof navigator === "undefined") return false;
  const n = navigator as Navigator & { userAgentData?: { brands?: { brand: string }[] } };
  if (n.webdriver === true) return true;
  if (AUTOMATED_UA.test(n.userAgent || "")) return true;
  return !!n.userAgentData?.brands?.some((b) => /headless/i.test(b.brand));
}

/** This device is marked internal (?internal=1 once, or a StratLab account signed in on it). */
export function internalDevice(): boolean {
  if (memoryMark !== null) return memoryMark;
  try { return localStorage.getItem(INTERNAL_KEY) === "1"; } catch { return false; }
}

/** Mark (or unmark) this device as internal. */
export function markInternal(on: boolean): void {
  memoryMark = on;
  try { if (on) localStorage.setItem(INTERNAL_KEY, "1"); else localStorage.removeItem(INTERNAL_KEY); } catch { /* storage off: this page view */ }
}

/** ?internal=1 (or 0) in the address: set or clear the mark, and say so on the page for a few seconds. Returns what it did. */
export function readInternalSwitch(search: string = typeof location === "undefined" ? "" : location.search): "on" | "off" | null {
  const v = new URLSearchParams(search).get("internal");
  if (v !== "1" && v !== "0") return null;
  markInternal(v === "1");
  if (typeof document !== "undefined" && document.body) {
    const note = document.createElement("div");
    note.setAttribute("role", "status");
    note.setAttribute("data-internal-note", v);
    note.textContent = v === "1" ? "This device is now left out of StratLab's analytics." : "This device is counted in StratLab's analytics again.";
    note.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:9999;background:#1D1B17;color:#F5F1E8;padding:10px 16px;border-radius:10px;font:14px/1.4 system-ui,sans-serif;max-width:calc(100vw - 32px)";
    document.body.appendChild(note);
    window.setTimeout(() => note.remove(), 6000);
  }
  return v === "1" ? "on" : "off";
}

/** The signed-in account is one of StratLab's own (the server's /me `internal`): left out, and the device marked. */
export function setAccountInternal(on: boolean): void {
  accountInternal = on;
  if (on) markInternal(true);
}

/** Nothing about this browser's visits goes to analytics (the browser's own wish, a robot, or StratLab's own people). */
export function analyticsOff(): boolean {
  return doNotTrack() || automated() || internalDevice() || accountInternal;
}

/** Where the visit came from, carried into the sign-up: ?from=stock|theme|blog|… on a link from a page the server draws, kept 30 days. */
const FROM_KEY = "stratlab.from";
const FROM = /^[a-z][a-z0-9_-]{0,23}$/;
export function rememberFrom(search: string = typeof location === "undefined" ? "" : location.search): void {
  const v = new URLSearchParams(search).get("from");
  if (!v || !FROM.test(v)) return;
  try { localStorage.setItem(FROM_KEY, JSON.stringify({ v, at: Date.now() })); } catch { /* storage off */ }
}
export function signupFrom(): string | null {
  try {
    const j = JSON.parse(localStorage.getItem(FROM_KEY) || "null");
    return j && typeof j.v === "string" && FROM.test(j.v) && Date.now() - j.at < 30 * 86_400_000 ? j.v : null;
  } catch { return null; }
}
