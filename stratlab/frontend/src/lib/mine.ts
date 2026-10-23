import { useEffect, useState } from "react";
import { api } from "./api";
import { happened, istHm, loadEvents, type EvKind } from "./marketEvents";
import type { Region } from "./research";
import { istToday } from "./format";

/* The data behind "My space" (/mine): only what the app already reads for its other pages, gathered. Nothing here is
 * made up: a figure that cannot be read stays null and the card shows an empty state with the next step. */

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const todayIso = () => iso(new Date());
export const addDaysIso = (s: string, n: number) => { const [y, m, d] = s.split("-").map(Number); const t = new Date(y, m - 1, d); t.setDate(t.getDate() + n); return iso(t); };

/* ---------- the market strip ---------- */
export interface MarketTile {
  id: string; label: string; /** where the closes come from */ from: { research: [Region, string] } | { instrument: string };
  /** how to write the level */ fmt: (v: number) => string; /** a rise is not good or bad news (a currency pair, gold) */ neutral?: boolean; unit?: string;
}
const grouped = (loc: string) => (v: number) => Math.round(v).toLocaleString(loc);
const fixed = (dp: number, pre = "") => (v: number) => pre + v.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp });
/** A share index's day move is green or red like any other change. A currency pair and gold keep a neutral look: a rise in
 * the dollar or in gold is not good or bad news by nature. */
export const MARKET_TILES: MarketTile[] = [
  { id: "nifty", label: "NIFTY 50", from: { research: ["IN", "^NSEI"] }, fmt: grouped("en-IN") },
  { id: "sensex", label: "SENSEX", from: { research: ["IN", "^BSESN"] }, fmt: grouped("en-IN") },
  { id: "banknifty", label: "NIFTY BANK", from: { research: ["IN", "^NSEBANK"] }, fmt: grouped("en-IN") },
  { id: "sp500", label: "S&P 500", from: { research: ["US", "^GSPC"] }, fmt: grouped("en-US") },
  { id: "usdinr", label: "USD/INR", from: { instrument: "FX:USDINR=X" }, fmt: fixed(2), neutral: true },
  { id: "gold", label: "Gold", from: { instrument: "CMDTY:GC=F" }, fmt: fixed(0, "$"), neutral: true, unit: "$/oz" },
];

/** Gold in rupees for 10 grams, from its dollars an ounce and the dollar in rupees (31.1035 grams to a troy ounce). */
export const goldInr10g = (usdPerOz: number, inrPerUsd: number) => (usdPerOz * inrPerUsd / 31.1035) * 10;

/** `day`: the session of the last close (its calendar day in the market's zone), so a move that isn't today's says its day. */
export interface Series { values: number[]; last: number; prev: number | null; changePct: number | null; day?: string | null }
type Candle = { c: number | null; t: string };

/** The tiles' markets' zones, for the day of their last candle. */
const TILE_TZ: Record<string, string> = { IN: "Asia/Kolkata", US: "America/New_York" };

/** "on 8 Oct" when a tile's last close is a session before today in its market (R7T-003: SENSEX showed 8 Oct's −1.44% as the
 * day's move after 9 Oct's open); null when it is today's. */
export function tileWhen(day: string | null | undefined, today: string, fmt: (iso: string) => string, closed = false, market = false, settling = false,
  roundClock = false): string | null {
  // just after the close the day's last trade isn't the close yet: said so, as the company page and the pulse do (R72-001:
  // "7,695 +0.46% on 19 Oct" beside "7,691 +0.41%, closing prints still settling")
  if (day && closed && settling && day === today) return "today, closing prints settling";
  // a session that has closed says its day too, today's included, as the tiles beside it do (R13-007: India's tiles said
  // "on 9 Oct" after their close while the S&P 500's, closed too, had no date)
  if (day && (day < today || closed)) return `on ${fmt(day)}`;
  // a market's index trading now says so, beside India's "on 19 Oct" (R71-003: "S&P 500 7,698 ▲ +0.51%" with no time)
  if (day && market && day === today) return "today, live";
  // a pair or a future that trades round the clock says its day too, beside the indices' labels (R77-006: USD/INR and
  // Gold had a change with no "today" or date)
  return day && roundClock && day === today ? "today" : null;
}

/** The session a watchlist mover's change is of, when it isn't today's in its market: the server's `change_day` (India
 * before the open), else the market day of the quote's own time when that is before today there (R79-005: NVDA +2.54%
 * on My space at 09:50 IST, the US's 21 Oct move, with no day beside the S&P 500's "on 21 Oct"). Null for today's move. */
export function moverDay(region: string, q: { change_day?: string | null; at?: string | null }, now = new Date(), closed = false): string | null {
  if (q.change_day) return q.change_day;
  const tz = TILE_TZ[region];
  if (!tz || !q.at) return null;
  const at = new Date(q.at);
  if (Number.isNaN(at.getTime())) return null;
  const day = at.toLocaleDateString("en-CA", { timeZone: tz }), today = now.toLocaleDateString("en-CA", { timeZone: tz });
  // today's session that has closed says its day too, as the S&P 500's tile does (R83-003: NVDA −4.40% at 09:19 IST,
  // still 22 Oct in New York, with no day beside TCS's live move)
  return day < today || (closed && day === today) ? day : null;
}

/** The market a tile's day is of, for whether its session has closed: the region of a research index; none for a pair or a
 * future that trades round the clock. */
export function tileMarket(t: MarketTile): string | null {
  return "research" in t.from ? t.from.research[0] : null;
}

/** Today's date in a tile's market. */
export function tileToday(t: MarketTile, now = new Date()): string {
  const tz = "research" in t.from ? TILE_TZ[t.from.research[0]] ?? "UTC" : "UTC";
  return now.toLocaleDateString("en-CA", { timeZone: tz });
}

const candleDay = (t: string, tz: string) => (/^\d{4}-\d{2}-\d{2}$/.test(t) ? t : /^\d{4}-\d{2}-\d{2}T00:00:00/.test(t) ? t.slice(0, 10) : new Date(t).toLocaleDateString("en-CA", { timeZone: tz }));
const seriesCache = new Map<string, { at: number; p: Promise<Series | null> }>();

function loadSeries(t: MarketTile): Promise<Series | null> {
  const hit = seriesCache.get(t.id);
  if (hit && Date.now() - hit.at < 5 * 60_000) return hit.p;
  const url = "research" in t.from
    ? `/research/chart/${t.from.research[0]}/${encodeURIComponent(t.from.research[1])}?tf=1d&range=1m`
    : `/chart/candles/${encodeURIComponent(t.from.instrument)}?tf=1d&range=1m`;
  const tz = "research" in t.from ? TILE_TZ[t.from.research[0]] ?? "UTC" : "UTC";
  const p = api<{ candles: Candle[] }>(url).then((r) => {
    const rows = (r.candles ?? []).filter((c): c is { c: number; t: string } => typeof c.c === "number" && Number.isFinite(c.c));
    const values = rows.map((c) => c.c);
    if (!values.length) return null;
    const last = values[values.length - 1], prev = values.length > 1 ? values[values.length - 2] : null;
    return { values, last, prev, changePct: prev ? (last / prev - 1) * 100 : null, day: candleDay(rows[rows.length - 1].t, tz) };
  }).catch(() => { seriesCache.delete(t.id); return null; });
  seriesCache.set(t.id, { at: Date.now(), p });
  return p;
}

/** Each tile's last month of daily closes: undefined while loading, null when it cannot be read. */
export function useMarketStrip(enabled = true): Record<string, Series | null | undefined> {
  const [out, setOut] = useState<Record<string, Series | null | undefined>>({});
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    MARKET_TILES.forEach((t) => loadSeries(t).then((s) => { if (live) setOut((o) => ({ ...o, [t.id]: s })); }));
    return () => { live = false; };
  }, [enabled]);
  return out;
}

/* ---------- coming up ---------- */
export interface Up { key: string; date: string; title: string; detail: string; to?: string; tag: string; tone: "warn" | "plain" }
type MoneyEv = { id: string; date: string; title: string; cat: string; kind: string; detail: string; amount: number | null; symbol: string | null; url: string | null };
type MoneyView = { events: MoneyEv[]; today: string; market_on?: boolean };
type ResultRow = { symbol: string; region: Region; date: string; purpose?: string; when?: string | null; out?: unknown };
type ResultsView = { today: string; weeks: { rows: ResultRow[] }[] };

const CAT_TAG: Record<string, string> = { tax: "Tax", holdings: "Your stocks", money: "Money", custom: "Yours", market: "Market" };
// exchange holidays too: the nearest market date that matters to anyone with a running paper session (R47-012)
const KINDS: EvKind[] = ["holiday", "rbi", "india", "us", "budget", "index"];

/** The dates ahead from every calendar the app has: the money calendar (tax, your stocks' results and dividends, your own
 * dates), the market events (RBI, data releases, the Fed, index changes) and results for your watchlist. null while loading. */
export function useComingUp(limit = 6, enabled = true): Up[] | null {
  const [rows, setRows] = useState<Up[] | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    const today = istToday(), end = addDaysIso(today, 75);
    Promise.all([
      api<MoneyView>(`/money/calendar?start=${today}&end=${end}`).catch(() => null),
      loadEvents(),
      ...(["IN", "US"] as Region[]).map((r) => api<ResultsView>(`/research/results?region=${r}&scope=mine`).catch(() => null)),
    ]).then(([money, ev, inRes, usRes]) => {
      if (!live) return;
      const out: Up[] = [];
      for (const e of money?.events ?? []) {
        if (e.date < today) continue;
        if (e.kind === "results_out") continue;          // results already filed are not "coming up" (R6O-016)
        out.push({ key: `${e.date}|${e.symbol ?? ""}|${/result/i.test(e.title) ? "results" : e.title.toLowerCase()}`, date: e.date, title: e.title, tag: CAT_TAG[e.cat] ?? "Money",
          detail: [e.detail, e.amount != null ? `₹${Math.round(e.amount).toLocaleString("en-IN")}` : ""].filter(Boolean).join(" · "), to: e.url ?? "/money/calendar", tone: e.cat === "tax" ? "warn" : "plain" });
      }
      // when the money calendar already carries the market events (its own switch), they are not listed twice
      // the nearest weekly expiry within a week too (R52-013: Monday's NIFTY expiry missing from "Next up"); later weeklies
      // come every week and would crowd the list
      const weekEnd = addDaysIso(today, 7), nowHm = istHm();
      // one for each index, NIFTY's and SENSEX's (R64-008: Thursday's SENSEX weekly was missing)
      const weekly = new Set<unknown>();
      const named = new Set<string>();
      for (const e of [...(ev?.events ?? [])].sort((a, b) => a.date.localeCompare(b.date)))
        if (e.kind === "expiry" && /weekly/i.test(e.title) && !happened(e, today, nowHm) && e.date <= weekEnd && !named.has(e.title)) { named.add(e.title); weekly.add(e); }
      if (ev && !money?.market_on) for (const e of ev.events) {
        if (happened(e, today, nowHm) || e.date > end || !(KINDS.includes(e.kind) || weekly.has(e))) continue;
        out.push({ key: `${e.date}|market|${e.title.toLowerCase()}`, date: e.date, title: e.title, detail: e.detail, to: "/trade/events", tag: "Market", tone: "plain" });
      }
      for (const v of [inRes, usRes]) for (const w of v?.weeks ?? []) for (const r of w.rows) {
        if (r.date < today || r.date > end || r.out) continue;
        out.push({ key: `${r.date}|${r.symbol}|results`, date: r.date, title: `${r.symbol} results`, detail: ["Among your stocks", r.when].filter(Boolean).join(" · "),
          to: `/research/${r.region}/${encodeURIComponent(r.symbol)}`, tag: "Results", tone: "plain" });
      }
      const seen = new Set<string>();
      setRows(out.sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title)).filter((u) => (seen.has(u.key) ? false : (seen.add(u.key), true))).slice(0, limit));
    });
    return () => { live = false; };
  }, [limit, enabled]);
  return rows;
}
