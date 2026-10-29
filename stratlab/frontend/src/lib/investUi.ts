/* Review 5c: the Invest and Research screens' small pieces with no page or request in them (the unit tests load this file
 * alone): the watchlist's quotes asked in batches, the Invest home's links carrying its market, a request counter that
 * keeps only the newest answer, the screener's and the rotation's choices in the address, and a brief's links into the app. */
import type { Bound, Filters, RangeId } from "./screens";

export type Region = "IN" | "US";

/* ---------- the watchlist's quotes ---------- */
/** The most symbols the server's quotes call answers in one request (backend intel/routes.py `quotes`): each one is a
 * read from a price source, so a longer list is asked for in turns, not all at once. */
export const QUOTE_BATCH = 24;

/** The list cut into runs of `size`, in order. */
export function batches<T>(xs: T[], size = QUOTE_BATCH): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < xs.length; i += Math.max(1, size)) out.push(xs.slice(i, i + Math.max(1, size)));
  return out;
}

/** Every symbol's quote, asked `size` at a time one request after another; `onPart` gets what has come so far after each
 * batch (each asked symbol present, null when it had no price), so the first rows fill in while the rest are asked. A
 * batch that fails leaves its symbols null and the next ones are still asked. `live()` false stops it (the page moved on). */
export async function quotesInBatches<Q>(ask: (syms: string[]) => Promise<Record<string, Q | null>>, syms: string[],
  onPart: (soFar: Record<string, Q | null>) => void, live: () => boolean = () => true, size = QUOTE_BATCH): Promise<Record<string, Q | null>> {
  let soFar: Record<string, Q | null> = {};
  for (const part of batches(syms, size)) {
    if (!live()) break;
    let got: Record<string, Q | null> = {};
    try { got = (await ask(part)) ?? {}; } catch { got = {}; }
    if (!live()) break;
    soFar = { ...soFar };
    for (const s of part) soFar[s] = got[s] ?? got[s.toUpperCase()] ?? null;
    onPart(soFar);
  }
  return soFar;
}

/* ---------- a request counter: only the newest answer is used ---------- */
/** `next()` before asking; `latest(n)` whether the answer for ticket `n` is still the one wanted (no newer ask, no reset). */
export function makeLatest() {
  let n = 0;
  return { next: () => ++n, latest: (t: number) => t === n, reset: () => { n++; } };
}

/** The compare page's request key: a late answer for another market or pair is never put on this one. */
export const pairKey = (region: Region, a: string, b: string) => `${region}|${a.toUpperCase()}|${b.toUpperCase()}`;

/* ---------- the Invest home's links ---------- */
/** An address with `region=` set (kept with whatever else it asks), so the page it opens shows the market picked. */
export function withRegion(to: string, region: Region): string {
  const [path, query = ""] = to.split("?");
  const p = new URLSearchParams(query);
  p.set("region", region);
  return `${path}?${p}`;
}

/** The Invest home's tool strip for the market picked: each card opens its page on that market. The trend scan's
 * ready-made group (the NIFTY 50) is India's: a US card opens the US scan on its own first group. */
export function investStrip(region: Region): { to: string; key: string }[] {
  return [
    { key: "screens", to: withRegion("/research/screens", region) },
    { key: "rotation", to: withRegion("/research/rotation", region) },
    { key: "scan", to: withRegion(region === "IN" ? "/research/scan?set=nifty50" : "/research/scan", region) },
    { key: "dividends", to: withRegion("/research/corporate-actions", region) },
  ];
}

/* ---------- a brief's links ---------- */
const IN_APP = /^\/(research|paper|news|account|invest|money|trade|calendar)(\/|$)/;
const bare = (host: string) => host.toLowerCase().replace(/^www\./, "");

/** A link in a brief that opens a page of this app: its path (with its query and #part) when it is on this site's own host
 * (with or without "www.") and names one of the app's pages; null for anything else, which opens in a new tab. */
export function inAppPath(href: string | null | undefined, here: { origin: string; host: string }): string | null {
  if (!href) return null;
  let u: URL;
  try { u = new URL(href, here.origin); } catch { return null; }
  if (bare(u.host) !== bare(here.host)) return null;
  return IN_APP.test(u.pathname) ? u.pathname + u.search + u.hash : null;
}

/* ---------- the screener's choices in the address ---------- */
export interface ScreenState { filters: Filters; sort: string; desc: boolean }
export const SCREEN_SORT = "market_cap";

/** The screen's conditions and sort as address parameters: `f` (the conditions set, as JSON), `sort` and `dir` (left out
 * at their defaults, the largest market value first), so Back returns to the same screen. */
export function screenQuery(s: ScreenState, none: Filters): Record<string, string | null> {
  const f = s.filters, out: Record<string, unknown> = {};
  for (const k of ["sector", "cap", "stage", "surv_lists"] as const) if ((f[k] ?? []).length) out[k] = f[k];
  for (const k of ["red_flags", "insider_buy", "surveillance"] as const) if (f[k]) out[k] = f[k];
  if (f.insider_days != null && f.insider_days !== none.insider_days) out.insider_days = f.insider_days;
  const ranges = Object.fromEntries(Object.entries(f.ranges ?? {}).filter(([, b]) => b && (b.min != null || b.max != null)));
  if (Object.keys(ranges).length) out.ranges = ranges;
  return {
    f: Object.keys(out).length ? JSON.stringify(out) : null,
    sort: s.sort && s.sort !== SCREEN_SORT ? s.sort : null,
    dir: s.desc ? null : "asc",
  };
}

const strs = (v: unknown) => (Array.isArray(v) ? v.filter((x) => typeof x === "string") as string[] : []);
const finite = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** The screen an address describes (see screenQuery); anything unreadable is left at its default. */
export function screenFromQuery(p: URLSearchParams, none: Filters): ScreenState {
  let raw: Record<string, unknown> = {};
  try { const v = JSON.parse(p.get("f") || "{}"); if (v && typeof v === "object" && !Array.isArray(v)) raw = v; } catch { /* a broken address: no conditions */ }
  const one = <T extends string>(v: unknown, ok: readonly T[]): T | null => (ok.includes(v as T) ? (v as T) : null);
  const ranges: Partial<Record<RangeId, Bound>> = {};
  if (raw.ranges && typeof raw.ranges === "object") {
    for (const [k, b] of Object.entries(raw.ranges as Record<string, { min?: unknown; max?: unknown }>)) {
      const min = finite(b?.min), max = finite(b?.max);
      if (min != null || max != null) ranges[k as RangeId] = { min, max };
    }
  }
  const filters: Filters = {
    ...none,
    sector: strs(raw.sector), cap: strs(raw.cap),
    stage: Array.isArray(raw.stage) ? (raw.stage as unknown[]).filter((x) => typeof x === "number") as number[] : [],
    red_flags: one(raw.red_flags, ["yes", "no"] as const), insider_buy: one(raw.insider_buy, ["yes", "no"] as const),
    insider_days: finite(raw.insider_days) ?? none.insider_days, surveillance: one(raw.surveillance, ["on", "off"] as const),
    surv_lists: strs(raw.surv_lists), ranges,
  };
  const sort = (p.get("sort") || SCREEN_SORT).replace(/[^a-z0-9_]/gi, "") || SCREEN_SORT;
  return { filters, sort, desc: p.get("dir") !== "asc" };
}

/* ---------- the rotation's choices in the address ---------- */
export interface RotationState { set: string; from: string | null; interval: "weekly" | "daily"; tail: number }
export const ROTATION_DEFAULT: RotationState = { set: "sectors", from: null, interval: "weekly", tail: 4 };

/** The rotation page's group (a sector's stocks when drilled into, with the group it was opened `from`), candle size and
 * trail, read from the address. */
export function rotationFromQuery(p: URLSearchParams): RotationState {
  const tail = Math.round(Number(p.get("trail")));
  return {
    set: p.get("set") || ROTATION_DEFAULT.set,
    from: p.get("from") || null,
    interval: p.get("iv") === "daily" ? "daily" : "weekly",
    tail: Number.isFinite(tail) && tail >= 1 && tail <= 12 ? tail : ROTATION_DEFAULT.tail,
  };
}

/** The same as address parameters, each left out at its default. */
export function rotationQuery(s: RotationState): Record<string, string | null> {
  return {
    set: s.set !== ROTATION_DEFAULT.set ? s.set : null,
    from: s.set.startsWith("sector:") && s.from ? s.from : null,
    iv: s.interval !== ROTATION_DEFAULT.interval ? s.interval : null,
    trail: s.tail !== ROTATION_DEFAULT.tail ? String(s.tail) : null,
  };
}

/** `p` with `changes` applied (null removes one); the same object back when nothing changes, so an address write that
 * changes nothing can be skipped. */
export function withParams(p: URLSearchParams, changes: Record<string, string | null>): URLSearchParams {
  const next = new URLSearchParams(p);
  for (const [k, v] of Object.entries(changes)) { if (v == null || v === "") next.delete(k); else next.set(k, v); }
  return next.toString() === p.toString() ? p : next;
}

/* ---------- the rotation chart's width ---------- */
/** The narrowest the rotation chart draws: below the 254 px a small phone's card leaves for it, so it never overflows. */
export const ROTATION_MIN_W = 220;
export const rotationWidth = (box: number) => Math.max(ROTATION_MIN_W, Math.floor(box || 0));
