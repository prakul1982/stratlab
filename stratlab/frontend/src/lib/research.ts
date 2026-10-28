import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./api";
import { SETTLING, focusParam } from "./researchFormat";

export type Region = "IN" | "US";
export const REGION_NAME: Record<Region, string> = { IN: "India", US: "United States" };
export interface MetricItem { label: string; value: number | null; unit: "x" | "%" | "%±" | "money" | "cr"; note?: string; dp?: number;
  /** shown instead of a figure: "n/m" for a growth rate off a tiny base (DD-018) */ text?: string }
export interface MetricGroup { title: string; items: MetricItem[] }
/** `similar`: how many near-repeats of this headline were folded into it (DE-017) */
export interface NewsItem { headline: string; url: string; source: string; at: string | null; similar?: number }
export interface Quote { price: number | null; change?: number | null; change_pct?: number | null; open?: number | null;
  high?: number | null; low?: number | null; prev_close?: number | null; volume?: number | null; at?: string | null;
  /** the session the change is of, when the market hasn't traded today (the last completed one) */ change_day?: string | null;
  /** "issue": a new listing's first session, changed against its issue price, not a previous close (DD-010) */ ref?: "issue" | null }
export interface SourceStatus { source: string; ok: boolean; error: string | null; /** what the source was for ("prices", "news"), said without its name */ what?: string[] }
export interface SeriesPoint { y: string; v: number }

export interface Company {
  region: Region; symbol: string; name: string; exchange: string | null; currency: string; logo: string | null;
  website: string | null; industry: string | null; facts: { label: string; value: string }[];
  market_cap: number | null; cap_note?: string | null; quote: Quote | null; range52: { low: number | null; high: number | null; since?: string | null };
  /** a company that no longer trades (merged or delisted): what became of it (DD-012) */ delisted?: import("./researchFormat").Delisted | null;
  margins: { gross: number | null; operating: number | null; net: number | null } | null;
  metrics: MetricGroup[];
  trend: { unit: string; revenue: SeriesPoint[]; profit: SeriesPoint[]; revenue_label: string; profit_label: string } | null;
  quarters?: { cols: string[]; sales: (number | null)[]; profit: (number | null)[]; opm: (number | null)[] } | null;
  /** `note`: two classes that moved by about the same amount in opposite directions, said as a holder moving class (R7O-012) */
  shareholding?: { as_of: string; rows: { label: string; value: number; change: number | null }[]; note?: string | null } | null;
  /** a bank, lender or insurer: no EBITDA margin or debt-to-equity, and the quarters' margin is the financing margin (R7O-001) */
  bank?: boolean;
  pros?: string[]; cons?: string[];
  /** each quarter dated by its filing, with its fiscal quarter ("Q2 FY27") and the filed GAAP diluted EPS (DD-030, DD-031) */
  earnings: { period: string; actual: number; estimate: number; surprise_pct: number | null; fiscal?: string; gaap?: number | null; from_filing?: boolean }[];
  /** what the estimates' EPS counts: "gaap", or "adjusted" (non-GAAP) for this company (DD-031) */ earnings_basis?: "gaap" | "adjusted" | null;
  next_earnings: { date: string; eps_estimate: number | null } | null;
  insider: { net: number; count?: number; rows: { name: string; change: number; date: string }[] } | null;
  peers: string[]; news: NewsItem[];
  about: { wiki: { title: string; description?: string; extract: string; url: string } | null; profile: string | null };
  sources: SourceStatus[]; links: { label: string; url: string; kind?: string }[];
  testable: boolean; instrument_id: string | null;
  as_of?: string | null; numbers_at?: string | null;     // when the prices were read; when the reported numbers were
  market_open?: boolean;                                   // false: the price is the last close (the market is shut)
  /** the trading day of the price (its last trade's, in the market's zone); null when the price has no time (review 5c) */
  quote_day?: string | null;
  /** the news request failed (not "no headlines"): the card says the news couldn't be loaded */
  news_failed?: boolean;
  /** "pre_open": India's pre-open price, read between 09:00 and 09:15 IST: indicative, not a close (R7T-004) */
  phase?: "pre_open" | "settling" | null;
  /** what a lean company answer left out (news, about, peers): fetched with `companyMore` (R10O-009) */
  lazy?: string[];
}

/** What a lean company page leaves for its second request. */
export interface CompanyMore { news: NewsItem[]; wiki: Company["about"]["wiki"]; peers: string[]; sources: SourceStatus[] }

/** A lean company answer with what it left out put in: the news, the encyclopedia entry, the peers, and the sources' status.
 * The two answers' sources are merged by label: one that failed in either request shows as failed (so a news read that
 * failed only in the second still says the news is missing). */
export function withMore(c: Company, m: CompanyMore): Company {
  const sources = [...c.sources];
  for (const s of m.sources) {
    const i = sources.findIndex((x) => x.source === s.source);
    if (i < 0) sources.push(s);
    else if (sources[i].ok && !s.ok) sources[i] = s;
  }
  return { ...c, news: m.news, peers: m.peers, about: { ...c.about, wiki: m.wiki }, sources, lazy: undefined };
}

export interface Idea { title: string; text: string; why: string }
/** One line of plain numbers next to the AI read (growth, price trend, debt and cash, margins and returns): worked
 *  out from reported results and prices, never from AI, and never a score. */
export interface FactRow { id: string; label: string; items: { label: string; text: string }[] }
export interface CompanyAI {
  summary: string; facts: FactRow[];
  valuation_note: string;
  bull: string[]; bear: string[]; segments: { label: string; share: number }[]; position: string; watch: string[];
  ideas: Idea[]; generated_at: number;
}
export interface Co { name: string; ticker: string }
export interface SectorAI {
  sector: string; summary: string; market_size: string; cagr: number | null; cagr_note: string;
  etfs: { ticker: string; name: string }[]; sub_themes: { name: string; detail: string }[]; core: string;
  clusters: { name: string; companies: Co[] }[];
  screen: { name: string; ticker: string; layer: string; one_line: string }[];
  value_chain: { layer: string; description: string; companies: Co[] }[];
  tailwinds: string[]; risks: string[]; generated_at: number;
  /** the listed companies the exchange puts in the theme's industries, A to Z (DE-013); `named`: the map names it too */
  exchange?: { industries: string[]; total: number; companies: { ticker: string; name: string; industry: string; named: boolean }[] } | null;
}
/** One index's tile. `day`: the session its level and change are of; `live`: today's while the market trades; `stale`: the
 * market trades today but this is still a previous session's level, so its change is never "today's" (R7T-003). */
export type PulseData = { indices: IndexLevel[]; headlines: NewsItem[]; missing?: string[]; pending?: boolean; read_at?: string | null };
export interface IndexLevel {
  name: string; price: number; change_pct: number | null; high52: number | null; from_high_pct: number | null;
  at?: string | null; day?: string | null; live?: boolean; stale?: boolean; settling?: boolean;
}

/** What a price read between a market's close and its settle point is called (R13-005: "Last close $336.68" at 16:12 ET,
 * the final close being $336.64): the company header, the scans and the watchlist say it the same way. */
export { SETTLING } from "./researchFormat";

/** A US share class with a dash, the one way the app writes it (R13-001: /research/US/BRK.B had no chart and a market value
 * $120B too low; the public pages already send BRK.B to BRK-B). Other tickers upper-cased, as typed. */
export function canonTicker(region: string, symbol: string): string {
  const s = String(symbol ?? "").trim().toUpperCase();
  if (String(region).toUpperCase() !== "US") {
    // an Indian symbol as a price site or a broker writes it (TCS.NS, TCS.BO, TCS-EQ, NSE:TCS) is the company's own symbol (RC5-010:
    // /research/IN/TCS.NS said no such company); a lone affix is left as typed
    const bare = s.replace(/^(?:NSE|BSE)\s*[:/]\s*|(?:\.NS|\.BO|\.NSE|\.BSE|-EQ)$/g, "").trim();
    return bare && bare !== s && !/(?:\.NS|\.BO|-EQ)$/.test(bare) ? bare : s;
  }
  const m = /^([A-Z][A-Z0-9]{0,5})[./]([A-Z])$/.exec(s);
  return m ? `${m[1]}-${m[2]}` : s;
}

/** "Last close, 9 Oct" over prices of a closed session; "Latest, closing prints still settling" while they settle; null for
 * a session still trading (R13-007: the US scan's prices had no date). `day` is the session's ISO date. */
export function closeLabel(day: string | null | undefined, opts: { settling?: boolean; open?: boolean; dayText: (iso: string) => string }): string | null {
  if (!day) return null;
  if (opts.settling) return `${SETTLING} · ${opts.dayText(day)}`;
  if (opts.open) return null;
  return `Last close, ${opts.dayText(day)}`;
}

/** Whether a price is a closed session's: the market isn't trading now, or the price's day is before today in its zone. */
export function sessionClosed(day: string | null | undefined, today: string, open: boolean): boolean {
  return !open || (!!day && day < today);
}

/** Whether a market's closing prints are still settling now: a trading day, between its close and 45 minutes after
 * (the public pages' and the server's settle step), in a market whose prices say so (the US). */
export function settlingNow(m: { id: string; tz: string; hours?: { close?: string | null } | null; holidays?: string[] } | null | undefined, now = new Date()): boolean {
  if (!m || m.id !== "US" || !m.hours?.close) return false;
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: m.tz, year: "numeric", month: "2-digit", day: "2-digit", weekday: "short",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  const wd = get("weekday"), iso = `${get("year")}-${get("month")}-${get("day")}`;
  if (wd === "Sat" || wd === "Sun" || (m.holidays ?? []).includes(iso)) return false;
  const [h, mi] = m.hours.close.split(":").map(Number);
  const mins = (+get("hour") % 24) * 60 + +get("minute"), close = h * 60 + mi;
  return mins >= close && mins < close + 45;
}

/** Whether a 52-week range can be this share's: the price within a third below its low or half above its high, as the
 * server checks it (R7T-001: Class A's $698,000-$806,102 beside BRK-B's $511). */
export const plausibleRange = (px: number, low: number, high: number) => low > 0 && high >= low && px >= low * 0.67 && px <= high * 1.5;

/** What a company's price is called and what its change is against: "Pre-open (indicative)" before India's 09:15 open (a
 * price from the pre-open auction, never a close, R7T-004), "Last close" while the market is shut, else the live price. */
export function priceLabel(c: Pick<Company, "market_open" | "phase" | "quote_day">, today?: string, dayText: (iso: string) => string = (d) => d): { label: string | null; since: string } {
  if (c.phase === "pre_open") return { label: "Pre-open (indicative)", since: "against the last close" };
  // between the US close and its settle point the price is the day's last prints, not yet its close (R13-005)
  if (c.phase === "settling") return { label: SETTLING, since: "on the day" };
  if (c.market_open === false) return { label: "Last close", since: "on the day" };
  // while the market trades, "today" only of today's price (review 5c): a price with no time says so, and an earlier
  // session's price says its day
  if (c.quote_day === null) return { label: "Time of this price unknown", since: "" };
  if (c.quote_day && today && c.quote_day !== today) return { label: "Not updated today yet", since: `on ${dayText(c.quote_day)}` };
  return { label: null, since: "today" };
}

/** The words under an index's change: "today" only for a live level of today's session; a previous session's level while
 * the market trades says it hasn't updated; out of hours, the session it is of ("on 8 Oct"). */
export function indexWhen(i: Pick<IndexLevel, "day" | "live" | "stale" | "settling">, dayText: (iso: string) => string): string {
  if (i.settling) return i.day ? `${dayText(i.day)} · closing prints still settling` : "closing prints still settling";
  if (i.stale) return i.day ? `${dayText(i.day)} close · not updated today yet` : "not updated today yet";
  if (i.live || i.live === undefined && i.day === undefined) return "today";
  return i.day ? `on ${dayText(i.day)}` : "last session";
}
export interface PulseAI {
  tone: string; hot: { name: string; ticker: string; why: string }[];
  flows: { title: string; detail: string; direction: "INFLOW" | "OUTFLOW" | "ROTATION" | "" }[];
  themes: { theme: string; detail: string; example: string }[]; generated_at: number; levels_at?: string | null;
  /** The mood worked out from the day's moves, and the headlines' main story (DD-001); absent on an older read. */
  mood?: string;
  /** Where the FII/DII figures the read quotes come from, when it quotes them (DD-001). */
  flows_source?: string;
}
export interface CompareAI {
  verdict: string; differences: string[];
  generated_at?: number; error?: string;
}
export interface WatchItem { region: Region; symbol: string; name: string | null }

/** How often, and how many times, a company page asks again for a read being written behind it (about two minutes). */
export const AI_POLL_MS = 3000;
export const AI_POLLS = 40;

export const researchApi = {
  /** The page asks lean: the price, header and tables first; the news, encyclopedia entry and peers come from `companyMore` (R10O-009). */
  company: (r: Region, s: string, lean = false) => api<Company>(`/research/company/${r}/${encodeURIComponent(s)}${lean ? "?lean=1" : ""}`),
  companyMore: (r: Region, s: string) => api<CompanyMore>(`/research/company/${r}/${encodeURIComponent(s)}/more`),
  /** The AI read, or an Error saying why there is none (an answer of "unavailable" is a 200 on the wire, so a page opening is never a failed request). */
  companyAI: async (r: Region, s: string, refresh = false, alive: () => boolean = () => true): Promise<CompanyAI> => {
    const base = `/research/company/${r}/${encodeURIComponent(s)}/ai`;
    // the page never waits on its read: a read not written yet is written behind the page and asked for again every few
    // seconds (R8O-007: company pages settled in 8 to 30 s); "Refresh" asks and waits, as asked
    for (let i = 0; ; i++) {
      const got = await api<CompanyAI | { unavailable: true; message: string } | { pending: true }>(refresh ? `${base}?refresh=true` : `${base}?background=true`);
      if ("unavailable" in got) throw new Error(got.message);
      if (!("pending" in got)) return got;
      if (!alive()) throw new Error("left the page");
      if (i >= AI_POLLS) throw new Error("The AI service is busy. Ask again in a minute.");
      await new Promise((ok) => setTimeout(ok, i === 0 ? 800 : i === 1 ? 1600 : AI_POLL_MS));      // a quick read shows quickly
    }
  },
  chart: (r: Region, s: string, range: string) =>
    api<{ currency: string; source: string; candles: { t: string; c: number }[] }>(`/research/chart/${r}/${encodeURIComponent(s)}?range=${range}`),
  quotes: (r: Region, syms: string[]) => api<Record<string, Quote | null>>(`/research/quotes?region=${r}&symbols=${syms.map(encodeURIComponent).join(",")}`),
  search: (r: Region, q: string) => api<{ symbol: string; name: string; exchange: string; region: Region }[]>(`/research/search?region=${r}&q=${encodeURIComponent(q)}`),
  /** `pending`: the server's first read of the levels since it started isn't back yet (ask again in a moment, R24-001) */
  pulse: (r: Region, focus = "") => api<PulseData>(`/research/pulse?region=${r}${focusParam(focus)}`),
  /** The market read, or an Error saying why there is none (like companyAI: "unavailable" is a 200 on the wire). */
  pulseAI: async (r: Region, focus = "", refresh = false): Promise<PulseAI> => {
    const got = await api<PulseAI | { unavailable: true; message: string }>(`/research/pulse/ai?region=${r}${focusParam(focus)}${refresh ? "&refresh=true" : ""}`);
    if ("unavailable" in got) throw new Error(got.message);
    return got;
  },
  sector: (r: Region, q: string, refresh = false) => api<SectorAI>(`/research/sector?region=${r}&q=${encodeURIComponent(q)}${refresh ? "&refresh=true" : ""}`),
  compare: (r: Region, a: string, b: string, refresh = false) => api<{ a: Company; b: Company; ai: CompareAI }>(`/research/compare?region=${r}&a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}${refresh ? "&refresh=true" : ""}`),
};

/* ---------- region preference ---------- */
export function savedRegion(): Region {
  try { return (localStorage.getItem("stratlab.research.region") as Region) === "US" ? "US" : "IN"; } catch { return "IN"; }
}
export function saveRegion(r: Region) {
  try { localStorage.setItem("stratlab.research.region", r); } catch { /* private window */ }
}

/** The page's market: ?region= when the address has one, else the last one picked. Picking one saves it and puts it in
 *  the address, so a shared link opens on the same market. */
export function useRegion(fallback?: Region): [Region, (r: Region) => void] {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("region")?.toUpperCase();
  const [region, setRegionState] = useState<Region>(fromUrl === "US" || fromUrl === "IN" ? fromUrl : fallback ?? savedRegion());
  const setRegion = (r: Region) => {
    setRegionState(r); saveRegion(r);
    const p = new URLSearchParams(params); p.set("region", r); setParams(p, { replace: true });
  };
  return [region, setRegion];
}

/* ---------- watchlist, shared across pages ---------- */
let watchCache: WatchItem[] | null = null;
let watchLoad: Promise<WatchItem[]> | null = null;
const watchSubs = new Set<(w: WatchItem[]) => void>();

/** Reads the saved list once (a second caller waits for the same read). A failed read rejects and leaves the cache empty,
 * so nothing is ever saved over a list that was not read. */
function loadWatch(): Promise<WatchItem[]> {
  if (watchCache) return Promise.resolve(watchCache);
  watchLoad ??= api<{ items: WatchItem[] }>("/research/watchlist")
    .then((r) => { watchCache = r.items; watchSubs.forEach((f) => f(r.items)); return r.items; })
    .finally(() => { watchLoad = null; });
  return watchLoad;
}

/* Market Watch's first list is this list (MWR1-007). Each side keeps its own copy for the life of the page, and a change that
 * is saved from a stale copy replaces the other side's: a stock added in the panel was lost when another was starred on a
 * company page, and the reverse. So a save here is announced, and Market Watch hands its copy over when it changes. */
const watchHear = new Set<() => void>();
/** `fn` is called after a change of the watchlist is saved from the Research pages; returns how to stop listening. */
export function onWatchlistSaved(fn: () => void): () => void {
  watchHear.add(fn);
  return () => { watchHear.delete(fn); };
}
/** The stocks and ETFs of the first Market Watch list as this list's copy, when it differs from it. */
export function adoptWatchlist(items: WatchItem[]): void {
  const key = (xs: WatchItem[]) => xs.map((i) => `${i.region}:${i.symbol}`).join(",");
  if (watchCache && key(watchCache) === key(items)) return;
  watchCache = items;
  watchSubs.forEach((f) => f(items));
}

/** What an add / remove / save says when the saved list could not be read first. */
export const WATCH_UNREAD = "Your watchlist couldn't be read, so nothing was changed. Try again.";

/** The saved list with a company added (`want` true) only when it isn't on it, or removed only when it is; the same list
 * (and `changed` false) when it already is as asked. */
export function watchChange(cur: WatchItem[], item: WatchItem, want: boolean): { list: WatchItem[]; changed: boolean } {
  const same = (i: WatchItem) => i.region === item.region && i.symbol === item.symbol;
  const on = cur.some(same);
  if (on === want) return { list: cur, changed: false };
  return { list: want ? [...cur, item] : cur.filter((i) => !same(i)), changed: true };
}

/** What a press of Watch or Remove says, from what happened to the saved list. */
export function watchNote(symbol: string, want: boolean, changed: boolean): string {
  if (want) return changed ? `${symbol} added to your watchlist.` : `${symbol} is already on your watchlist.`;
  return changed ? `${symbol} removed from your watchlist.` : `${symbol} isn't on your watchlist.`;
}

export function useWatchlist() {
  const [items, setItems] = useState<WatchItem[] | null>(watchCache);
  const [failed, setFailed] = useState(false);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    watchSubs.add(setItems);
    let live = true;
    if (!watchCache) { setFailed(false); loadWatch().then(() => live && setFailed(false)).catch(() => live && setFailed(true)); }
    return () => { live = false; watchSubs.delete(setItems); };
  }, [tries]);
  /** Never saves while the saved list is unread: a failed first read would otherwise turn one press of Watch into a
   * one-company list that replaces the whole watchlist. The list is read first, or the change is refused. */
  const save = useCallback(async (next: WatchItem[] | ((cur: WatchItem[]) => WatchItem[])) => {
    let cur: WatchItem[];
    try { cur = await loadWatch(); } catch { throw new Error(WATCH_UNREAD); }
    const list = typeof next === "function" ? next(cur) : next;
    if (list === cur) return;                     // nothing to change: no save
    const prev = watchCache;
    watchCache = list; watchSubs.forEach((f) => f(list));
    try { await api("/research/watchlist", { method: "PUT", body: { items: list } }); watchHear.forEach((f) => f()); }
    catch (e) { watchCache = prev; watchSubs.forEach((f) => f(prev ?? [])); throw e; }
  }, []);
  const has = (r: Region, s: string) => !!items?.some((i) => i.region === r && i.symbol === s);
  /** Adds (`want` true) or removes a company, as the reader asked, on the list as read: a press of "Watch" on a list not
   * yet read never removes a company already saved. Resolves to whether the list changed (watchNote says which). */
  const toggle = async (item: WatchItem, want: boolean): Promise<boolean> => {
    let changed = false;
    await save((cur) => { const r = watchChange(cur, item, want); changed = r.changed; return r.list; });
    return changed;
  };
  /** `failed`: the first read did not work and there is nothing to show; `retry` reads it again. */
  return { items, has, toggle, save, failed: failed && items === null, retry: () => setTries((n) => n + 1) };
}

/* ---------- formatting ---------- */
/* Big money in the units people say ($4.31T, ₹1.51 lakh cr): bigMoney, in format.ts. Units for groups of amounts,
 * trend values and metric figures: researchFormat.ts (no browser needed, so the unit tests read them). */
export { bigMoney } from "./format";
export { focusParam, holderRowName, linkLabel, metricText, missingLine, missingWhat, millionsOf, monthsOld, newsAge, newsWhen, periodEnd, pulseClosedDay, pulseLede, resultsFiled, scaleFor, screenCap, screenNum, staleQuarter, trendShort, trendValue, usdAmount, type Scale } from "./researchFormat";

/* ---------- where a number sits in a typical range (from Hindsight) ----------
 * [floor, weak edge, strong edge, ceiling, higher-is-better]. Loose large-cap defaults,
 * widened or narrowed for industries where the normal range is different. */
type Band = [number, number, number, number, boolean];
const BANDS: Record<string, Band> = {
  "P/E": [0, 12, 30, 70, false], "Fwd P/E": [0, 10, 26, 60, false], "P/S": [0, 1.5, 6, 20, false], "P/B": [0, 1.5, 6, 50, false],
  "EV/EBITDA": [0, 7, 18, 45, false], "EV/FCF": [0, 12, 30, 70, false], "PEG (fwd)": [0, 1, 2.5, 5, false],
  "Gross margin": [0, 25, 45, 90, true], "Operating margin": [-10, 8, 22, 55, true], "Net margin": [-10, 5, 18, 45, true],
  "OPM": [-10, 8, 22, 55, true], "EBITDA margin": [-10, 8, 22, 55, true], "ROE": [-10, 8, 20, 60, true], "ROA": [-5, 3, 10, 35, true], "ROCE": [-5, 8, 20, 50, true],
  "Revenue YoY": [-25, 0, 10, 45, true], "EPS YoY": [-40, 0, 12, 70, true], "Revenue 3Y": [-15, 0, 8, 35, true],
  "Revenue 5Y": [-15, 0, 8, 35, true], "EPS 5Y": [-25, 0, 10, 45, true], "Latest YoY": [-25, 0, 10, 45, true],
  "3Y CAGR": [-15, 0, 10, 35, true], "5Y CAGR": [-15, 0, 10, 35, true], "10Y CAGR": [-10, 0, 10, 30, true],
  "Current ratio": [0, 1, 2, 4, true], "LT debt / equity": [0, 0.5, 1.5, 3, false], "Long-term debt / equity": [0, 0.5, 1.5, 3, false], "Debt / equity": [0, 0.5, 1.5, 3, false], "Total debt / equity": [0, 0.5, 1.5, 3, false],
  "Interest coverage": [0, 3, 10, 30, true], "Asset turnover": [0, 0.4, 1, 2.5, true], "Beta": [0, 0.8, 1.4, 2.5, false],
  "1Y return": [-50, 0, 15, 90, true], "Div yield": [0, 0.5, 2.5, 7, true], "Payout ratio": [0, 20, 70, 120, false],
};
const SCALE: Record<string, Record<string, number>> = {
  software: { "P/S": 2.2, "P/B": 2, "P/E": 1.4 }, technology: { "P/S": 1.8, "P/B": 1.8, "P/E": 1.3 },
  semiconductors: { "P/S": 2, "P/B": 1.8, "P/E": 1.3 }, biotechnology: { "P/S": 3, "P/E": 2 },
  bank: { "P/B": 0.4, "P/S": 0.5, "Gross margin": 0.6 }, insurance: { "P/B": 0.5, "P/S": 0.4 },
  "real estate": { "P/B": 0.6, "LT debt / equity": 2, "Long-term debt / equity": 2 }, utilities: { "LT debt / equity": 2, "Long-term debt / equity": 2, "Revenue YoY": 0.5 },
  retail: { "Gross margin": 0.6, "Net margin": 0.5, "P/S": 0.4 }, energy: { "Revenue YoY": 1.6, "P/E": 0.7 },
  automobiles: { "Gross margin": 0.5, "Net margin": 0.5, "P/S": 0.5 },
};

export function bandPosition(label: string, value: number | null, industry?: string | null): { pos: number; weak: number; strong: number; tone: "good" | "bad" | "mid" } | null {
  const b = BANDS[label];
  if (!b || value == null) return null;
  let f = 1;
  const ind = (industry || "").toLowerCase();
  for (const k in SCALE) if (ind.includes(k) && SCALE[k][label]) { f = SCALE[k][label]; break; }
  const [lo, weak, strong, hi, higher] = f === 1 ? b : [b[0] * f, b[1] * f, b[2] * f, b[3] * f, b[4]] as Band;
  const at = (v: number) => Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));
  const good = higher ? value >= strong : value <= weak;
  const bad = higher ? value <= weak : value >= strong;
  return { pos: Math.max(2.5, Math.min(97.5, at(value))), weak: at(weak), strong: at(strong), tone: good ? "good" : bad ? "bad" : "mid" };
}

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export const THEME_IDEAS: Record<Region, string[]> = {
  IN: ["India defence", "Railways capex", "Renewables and solar", "EV and battery supply chain", "Digital payments", "Specialty chemicals"],
  US: ["AI data centers", "Grid electrification", "Nuclear and SMRs", "GLP-1 supply chain", "Defense drones", "Cybersecurity"],
};
export const STARTER_TICKERS: Record<Region, string[]> = {
  IN: ["RELIANCE", "TCS", "HDFCBANK", "INFY", "BHARTIARTL", "LT"],
  US: ["NVDA", "AAPL", "MSFT", "VRT", "CEG", "ASML"],
};
