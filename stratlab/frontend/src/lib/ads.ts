/* Ads and analytics that need the visitor's yes (ADS-1): Google ads, the Meta Pixel and Microsoft Clarity. One question ("Allow" /
 * "No thanks"), one saved answer; when a slot shows an ad, a StratLab card or nothing, and which pages may load a tracker at all.
 * No React and no imports of the account code, so the public pages use it and unit/ads.test.mjs reads it as it is.
 *
 * Off by default: an ad needs the switch on (ADS_ENABLED), the publisher ID (ca-pub-…) and that slot's ID, and then the
 * visitor's "Allow ads". The settings come from the build (VITE_ADSENSE_CLIENT, VITE_ADSENSE_SLOT_PUBLIC, VITE_ADSENSE_SLOT_AI,
 * VITE_ADS_ENABLED) and, over them, from /config.js (the same names without VITE_), which turns ads off again without a rebuild.
 * The server-rendered pages have their own copy of the same settings (backend/app/ads.py); public/ads.js shares this file's
 * answer key. Two slots exist: "public" for signed-out visitors on public pages, and "ai" for Free accounts under an AI answer. */
import { LIMITS } from "./plans";

export type Choice = "yes" | "no" | null;
export type AdSlotName = "public" | "ai";
export type AdMode = "ad" | "house" | "none";
export interface AdsConfig {
  on: boolean; client: string; slots: Record<AdSlotName, string>;
  /** Meta Pixel ID (digits), "" = no pixel. Nothing by default. */
  pixel: string;
  /** Microsoft Clarity project ID, "" = no Clarity. The owner's project by default; an empty setting turns it off. */
  clarity: string;
}

/** Where the visitor's answer is kept (public/ads.js writes the same key and format). */
export const CHOICE_KEY = "stratlab.ads";
/** An answer stands for a year, then the question is asked again. */
export const CHOICE_DAYS = 365;

const CLIENT = /^ca-pub-\d{10,20}$/;
/** The owner's AdSense publisher ID (public, not a secret): the default, so only the slot IDs and the switch are left to set. */
export const DEFAULT_CLIENT = "ca-pub-8125241692814953";
/** The owner's Clarity project (public, not a secret). It loads only after "Allow", and never on the pages in TRACK_NEVER. */
export const DEFAULT_CLARITY = "z4n5s4xn12";
const PIXEL = /^\d{5,20}$/;
const CLARITY = /^[a-z0-9]{6,16}$/;
const SLOT = /^\d{6,20}$/;

/** The settings from the build's env (VITE_…) with /config.js over them. A value that isn't an ID counts as not set; no publisher
 * ID at all means the owner's (DEFAULT_CLIENT). Names: ADS_ENABLED, ADSENSE_CLIENT, ADSENSE_SLOT_PUBLIC, ADSENSE_SLOT_AI, META_PIXEL_ID
 * (env: VITE_META_PIXEL_ID) and CLARITY_PROJECT_ID (env: VITE_CLARITY_ID); Clarity is the owner's project unless set, and set to
 * "" it is off. */
export function adsConfig(env: Record<string, unknown> = {}, runtime: Record<string, unknown> = {}): AdsConfig {
  const pick = (name: string) => String(runtime[name] ?? env[`VITE_${name}`] ?? "").trim();
  const id = (name: string, re: RegExp) => { const v = pick(name); return re.test(v) ? v : ""; };
  const clarityRaw = runtime.CLARITY_PROJECT_ID ?? env.VITE_CLARITY_ID;
  const clarity = clarityRaw === undefined || clarityRaw === null ? DEFAULT_CLARITY : String(clarityRaw).trim();
  return { on: pick("ADS_ENABLED").toLowerCase() === "true", client: pick("ADSENSE_CLIENT") ? id("ADSENSE_CLIENT", CLIENT) : DEFAULT_CLIENT,
    slots: { public: id("ADSENSE_SLOT_PUBLIC", SLOT), ai: id("ADSENSE_SLOT_AI", SLOT) },
    pixel: id("META_PIXEL_ID", PIXEL), clarity: CLARITY.test(clarity) ? clarity : "" };
}

/** Ads can draw in this slot: the switch is on and both IDs are set. */
export const adsLive = (cfg: AdsConfig, slot: AdSlotName): boolean => !!(cfg.on && cfg.client && cfg.slots[slot]);

/** The pages that hold someone's own money, account or payment, or that are the way in: never an ad, whatever else says so. */
const NEVER = /^\/(money|holdings|tax-report|net-?worth|account|settings|admin|login|signup|upgrade|plans|pricing|checkout|invite|import|alerts|assistant|app|paper|options|n|notebooks|mine)(\/|$)/;
export const adsAllowedOn = (path: string): boolean => !NEVER.test(path.split(/[?#]/)[0]);

/** The pages where no tracker (Meta Pixel, Clarity) loads or sends anything, and where the question isn't asked: money, tax, holdings,
 * net worth, account and settings, admin, and the way in and the payment. A tracker already loaded stops here (Clarity is stopped,
 * the pixel sends no event). The ad slots have their own, longer list (NEVER). */
const TRACK_NEVER = /^\/(money|holdings|tax-report|net-?worth|account|settings|admin|checkout|upgrade|plans|login|signup)(\/|$)/;
export const trackAllowedOn = (path: string): boolean => !TRACK_NEVER.test(path.split(/[?#]/)[0]);

/** Something needs the visitor's yes: an ad can draw, or a pixel or Clarity is set. With none of these nothing is ever asked. */
export const askNeeded = (cfg: AdsConfig): boolean => !!(adsLive(cfg, "public") || adsLive(cfg, "ai") || cfg.pixel || cfg.clarity);

/** What to load now. Needs the saved yes, a page that allows trackers, and a browser that doesn't ask not to be tracked (Do Not
 * Track, Global Privacy Control: the same rule as the usage analytics). */
export function trackersFor(o: { cfg: AdsConfig; choice: Choice; path: string; dnt?: boolean }): { pixel: boolean; clarity: boolean } {
  const ok = o.choice === "yes" && !o.dnt && trackAllowedOn(o.path);
  return { pixel: ok && !!o.cfg.pixel, clarity: ok && !!o.cfg.clarity };
}

/** The question is shown: something needs a yes, none was given, and the page is not one of the private ones. */
export const askNow = (o: { cfg: AdsConfig; choice: Choice; path: string }): boolean => askNeeded(o.cfg) && o.choice === null && trackAllowedOn(o.path);

/** The question's words, naming only what is switched on. */
export function consentWords(cfg: AdsConfig): { title: string; text: string } {
  const ads = adsLive(cfg, "public") || adsLive(cfg, "ai");
  const parts = [ads && "Google ads", cfg.pixel && "Meta's ad measurement", cfg.clarity && "Microsoft Clarity, which records how pages are used with all text hidden"].filter(Boolean) as string[];
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0] ?? "";
  const title = ads && (cfg.pixel || cfg.clarity) ? "Ads and analytics" : ads ? "Ads" : "Analytics";
  return { title, text: `With your OK, StratLab uses ${list}. They set cookies. Say no and none of them load. Never on money, tax, holdings, net worth or account pages.` };
}

/** A sign-up: the account was made in the last 15 minutes (as lib/analytics trackSignup counts it). */
export const isNewSignUp = (createdAt: string | null | undefined, now = Date.now()): boolean => {
  const t = createdAt ? new Date(createdAt).getTime() : NaN;
  return Number.isFinite(t) && now - t <= 15 * 60_000;
};

/** The visitor's saved answer from the stored text: "yes" or "no", or null for no answer, a damaged one or one over a year old. */
export function parseChoice(raw: string | null | undefined, now = Date.now()): Choice {
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as { c?: unknown; at?: unknown };
    if ((j.c === "yes" || j.c === "no") && typeof j.at === "number" && now - j.at < CHOICE_DAYS * 864e5) return j.c;
  } catch { /* not ours */ }
  return null;
}
export const encodeChoice = (c: "yes" | "no", now = Date.now()): string => JSON.stringify({ c, at: now });

let memory: Choice = null;      // the answer for this page view when storage is off
export function readChoice(): Choice {
  try { const raw = localStorage.getItem(CHOICE_KEY); if (raw) return parseChoice(raw); } catch { /* storage off */ }
  return memory;
}
const listeners = new Set<() => void>();
/** Runs `fn` when the answer is given or taken back on this page (a slot and the banner follow it). Returns the way to stop. */
export function onChoice(fn: () => void): () => void { listeners.add(fn); return () => { listeners.delete(fn); }; }
export function writeChoice(c: "yes" | "no"): void {
  memory = c;
  try { localStorage.setItem(CHOICE_KEY, encodeChoice(c)); } catch { /* storage off: kept for this page view only */ }
  listeners.forEach((fn) => fn());
}
/** Forget the answer, so the question comes back (Privacy: "Change my choice"). */
export function clearChoice(): void {
  memory = null;
  try { localStorage.removeItem(CHOICE_KEY); } catch { /* storage off */ }
  listeners.forEach((fn) => fn());
}

/** Google's own consent message (AdSense, Privacy & messaging) is on the page. It asks EEA and UK visitors, so ours steps aside. */
export function googleMessageShown(): boolean {
  try { return !!(window as unknown as { googlefc?: unknown }).googlefc || !!document.querySelector('iframe[name="googlefcPresent"]'); } catch { return false; }
}

export interface AdContext {
  slot: AdSlotName; cfg: AdsConfig; path: string; choice: Choice;
  /** "public": someone with a saved sign-in in this browser. "ai": the plan the account is on now; null while it is unknown. */
  signedIn: boolean; plan: "free" | "basic" | "pro" | null;
  /** Google's consent message is shown (googleMessageShown) */
  cmp?: boolean;
}

/** What a slot shows.
 * - "ai": Free accounts only (never Basic or Pro, and nothing while the plan is unknown). With ads off, before an answer or after
 *   "No thanks", a StratLab card (our own words, nothing tracked) holds the place.
 * - "public": signed-out visitors only, and only when ads can draw and the visitor said yes; otherwise nothing at all.
 * - never on the pages in NEVER. The question itself is the banner (components/Tracking.tsx), not part of the slot. */
export function adMode(c: AdContext): AdMode {
  if (!adsAllowedOn(c.path)) return "none";
  if (c.slot === "ai") { if (c.plan !== "free") return "none"; }
  else if (c.signedIn || c.plan) return "none";
  const own = c.slot === "ai" ? "house" : "none";
  if (!adsLive(c.cfg, c.slot)) return own;
  if (c.choice === "yes" || (c.cmp && c.choice !== "no")) return "ad";
  return own;
}

export interface HouseCard { id: "plans" | "luck" | "brief"; title: string; text: string; to: string; cta: string }
/** The cards that hold a Free account's slot while ads are off: StratLab's own pages, in plain facts. */
export const HOUSE: HouseCard[] = [
  { id: "plans", title: "Basic has more AI builds and deep dives",
    text: `Free includes ${LIMITS.free.ai_builds_per_month} AI strategy builds and ${LIMITS.free.deepdives_per_month} company deep dives a month. Basic includes ${LIMITS.basic.ai_builds_per_month} and ${LIMITS.basic.deepdives_per_month}, and has no ads.`,
    to: "/plans", cta: "See the plans" },
  { id: "luck", title: "Test your idea with the four luck checks",
    text: "Describe a rule in plain words. StratLab runs it on years of real prices and asks whether it held up on prices it never saw.",
    to: "/new", cta: "Test an idea" },
  { id: "brief", title: "Read today's market brief",
    text: "A short brief after each market close, for India, the US and the companies you follow.",
    to: "/news", cta: "Open the briefs" },
];

/** One card for a page, the same every time for the same `seed` (a company's symbol), so the card does not change as the page redraws. */
export function houseCard(seed: string): HouseCard {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return HOUSE[h % HOUSE.length];
}
