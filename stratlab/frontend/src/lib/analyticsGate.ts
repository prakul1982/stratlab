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

/** The signed-in account is one of StratLab's own (the server's /me `internal`): left out, and the device marked. */
export function setAccountInternal(on: boolean): void {
  accountInternal = on;
  if (on) markInternal(true);
}

/** Nothing about this browser's visits goes to analytics (the browser's own wish, a robot, or StratLab's own people). */
export function analyticsOff(): boolean {
  return doNotTrack() || automated() || internalDevice() || accountInternal;
}
