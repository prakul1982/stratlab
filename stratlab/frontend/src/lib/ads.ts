/* Ads (ADS-1): when a slot shows an ad, a question, a StratLab card or nothing. No React and no imports of the account code, so
 * the public pages use it and unit/ads.test.mjs reads it as it is.
 *
 * Off by default: an ad needs the switch on (ADS_ENABLED), the publisher ID (ca-pub-…) and that slot's ID, and then the
 * visitor's "Allow ads". The settings come from the build (VITE_ADSENSE_CLIENT, VITE_ADSENSE_SLOT_PUBLIC, VITE_ADSENSE_SLOT_AI,
 * VITE_ADS_ENABLED) and, over them, from /config.js (the same names without VITE_), which turns ads off again without a rebuild.
 * The server-rendered pages have their own copy of the same settings (backend/app/ads.py); public/ads.js shares this file's
 * answer key. Two slots exist: "public" for signed-out visitors on public pages, and "ai" for Free accounts under an AI answer. */
import { LIMITS } from "./plans";

export type Choice = "yes" | "no" | null;
export type AdSlotName = "public" | "ai";
export type AdMode = "ad" | "consent" | "house" | "none";
export interface AdsConfig { on: boolean; client: string; slots: Record<AdSlotName, string> }

/** Where the visitor's answer is kept (public/ads.js writes the same key and format). */
export const CHOICE_KEY = "stratlab.ads";
/** An answer stands for a year, then the question is asked again. */
export const CHOICE_DAYS = 365;

const CLIENT = /^ca-pub-\d{10,20}$/;
/** The owner's AdSense publisher ID (public, not a secret): the default, so only the slot IDs and the switch are left to set. */
export const DEFAULT_CLIENT = "ca-pub-8125241692814953";
const SLOT = /^\d{6,20}$/;

/** The settings from the build's env (VITE_…) with /config.js over them. A value that isn't an ID counts as not set; no publisher
 * ID at all means the owner's (DEFAULT_CLIENT). */
export function adsConfig(env: Record<string, unknown> = {}, runtime: Record<string, unknown> = {}): AdsConfig {
  const pick = (name: string) => String(runtime[name] ?? env[`VITE_${name}`] ?? "").trim();
  const id = (name: string, re: RegExp) => { const v = pick(name); return re.test(v) ? v : ""; };
  return { on: pick("ADS_ENABLED").toLowerCase() === "true", client: pick("ADSENSE_CLIENT") ? id("ADSENSE_CLIENT", CLIENT) : DEFAULT_CLIENT,
    slots: { public: id("ADSENSE_SLOT_PUBLIC", SLOT), ai: id("ADSENSE_SLOT_AI", SLOT) } };
}

/** Ads can draw in this slot: the switch is on and both IDs are set. */
export const adsLive = (cfg: AdsConfig, slot: AdSlotName): boolean => !!(cfg.on && cfg.client && cfg.slots[slot]);

/** The pages that hold someone's own money, account or payment, or that are the way in: never an ad, whatever else says so. */
const NEVER = /^\/(money|holdings|tax-report|net-?worth|account|settings|admin|login|signup|upgrade|plans|pricing|checkout|invite|import|alerts|assistant|app|paper|options|n|notebooks|mine)(\/|$)/;
export const adsAllowedOn = (path: string): boolean => !NEVER.test(path.split(/[?#]/)[0]);

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
export function writeChoice(c: "yes" | "no"): void {
  memory = c;
  try { localStorage.setItem(CHOICE_KEY, encodeChoice(c)); } catch { /* storage off: kept for this page view only */ }
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
 * - "ai": Free accounts only (never Basic or Pro, and nothing while the plan is unknown). With ads off, or after "No thanks",
 *   a StratLab card (our own words, nothing tracked) holds the place.
 * - "public": signed-out visitors only, and only when ads can draw; otherwise nothing at all.
 * - never on the pages in NEVER. */
export function adMode(c: AdContext): AdMode {
  if (!adsAllowedOn(c.path)) return "none";
  if (c.slot === "ai") { if (c.plan !== "free") return "none"; }
  else if (c.signedIn || c.plan) return "none";
  const own = c.slot === "ai" ? "house" : "none";
  if (!adsLive(c.cfg, c.slot)) return own;
  if (c.choice === "no") return own;
  if (c.choice === "yes" || c.cmp) return "ad";
  return "consent";
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
