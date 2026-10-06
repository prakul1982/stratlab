import { useEffect, useState } from "react";
import { api } from "./api";
import { loadEvents, type EvKind } from "./marketEvents";
import type { Region } from "./research";

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
export const MARKET_TILES: MarketTile[] = [
  { id: "nifty", label: "NIFTY 50", from: { research: ["IN", "^NSEI"] }, fmt: grouped("en-IN") },
  { id: "sensex", label: "SENSEX", from: { research: ["IN", "^BSESN"] }, fmt: grouped("en-IN") },
  { id: "banknifty", label: "BANK NIFTY", from: { research: ["IN", "^NSEBANK"] }, fmt: grouped("en-IN") },
  { id: "sp500", label: "S&P 500", from: { research: ["US", "^GSPC"] }, fmt: grouped("en-US") },
  { id: "usdinr", label: "USD/INR", from: { instrument: "FX:USDINR=X" }, fmt: fixed(2, "₹"), neutral: true },
  { id: "gold", label: "Gold", from: { instrument: "CMDTY:GC=F" }, fmt: fixed(0, "$"), neutral: true, unit: "per ounce" },
];

export interface Series { values: number[]; last: number; prev: number | null; changePct: number | null }
type Candle = { c: number | null; t: string };
const seriesCache = new Map<string, { at: number; p: Promise<Series | null> }>();

function loadSeries(t: MarketTile): Promise<Series | null> {
  const hit = seriesCache.get(t.id);
  if (hit && Date.now() - hit.at < 5 * 60_000) return hit.p;
  const url = "research" in t.from
    ? `/research/chart/${t.from.research[0]}/${encodeURIComponent(t.from.research[1])}?tf=1d&range=1m`
    : `/chart/candles/${encodeURIComponent(t.from.instrument)}?tf=1d&range=1m`;
  const p = api<{ candles: Candle[] }>(url).then((r) => {
    const values = (r.candles ?? []).map((c) => c.c).filter((x): x is number => typeof x === "number" && Number.isFinite(x));
    if (!values.length) return null;
    const last = values[values.length - 1], prev = values.length > 1 ? values[values.length - 2] : null;
    return { values, last, prev, changePct: prev ? (last / prev - 1) * 100 : null };
  }).catch(() => { seriesCache.delete(t.id); return null; });
  seriesCache.set(t.id, { at: Date.now(), p });
  return p;
}

/** Each tile's last month of daily closes: undefined while loading, null when it cannot be read. */
export function useMarketStrip(): Record<string, Series | null | undefined> {
  const [out, setOut] = useState<Record<string, Series | null | undefined>>({});
  useEffect(() => {
    let live = true;
    MARKET_TILES.forEach((t) => loadSeries(t).then((s) => { if (live) setOut((o) => ({ ...o, [t.id]: s })); }));
    return () => { live = false; };
  }, []);
  return out;
}

/* ---------- coming up ---------- */
export interface Up { key: string; date: string; title: string; detail: string; to?: string; tag: string; tone: "warn" | "plain" }
type MoneyEv = { id: string; date: string; title: string; cat: string; kind: string; detail: string; amount: number | null; symbol: string | null; url: string | null };
type MoneyView = { events: MoneyEv[]; today: string; market_on?: boolean };
type ResultRow = { symbol: string; region: Region; date: string; purpose?: string; when?: string | null; out?: unknown };
type ResultsView = { today: string; weeks: { rows: ResultRow[] }[] };

const CAT_TAG: Record<string, string> = { tax: "Tax", holdings: "Your stocks", money: "Money", custom: "Yours", market: "Market" };
const KINDS: EvKind[] = ["rbi", "india", "us", "budget", "index"];

/** The dates ahead from every calendar the app has: the money calendar (tax, your stocks' results and dividends, your own
 * dates), the market events (RBI, data releases, the Fed, index changes) and results for your watchlist. null while loading. */
export function useComingUp(limit = 6): Up[] | null {
  const [rows, setRows] = useState<Up[] | null>(null);
  useEffect(() => {
    let live = true;
    const today = todayIso(), end = addDaysIso(today, 75);
    Promise.all([
      api<MoneyView>(`/money/calendar?start=${today}&end=${end}`).catch(() => null),
      loadEvents(),
      ...(["IN", "US"] as Region[]).map((r) => api<ResultsView>(`/research/results?region=${r}&scope=mine`).catch(() => null)),
    ]).then(([money, ev, inRes, usRes]) => {
      if (!live) return;
      const out: Up[] = [];
      for (const e of money?.events ?? []) {
        out.push({ key: `${e.date}|${e.symbol ?? ""}|${/result/i.test(e.title) ? "results" : e.title.toLowerCase()}`, date: e.date, title: e.title, tag: CAT_TAG[e.cat] ?? "Money",
          detail: [e.detail, e.amount != null ? `₹${Math.round(e.amount).toLocaleString("en-IN")}` : ""].filter(Boolean).join(" · "), to: e.url ?? "/money/calendar", tone: e.cat === "tax" ? "warn" : "plain" });
      }
      // when the money calendar already carries the market events (its own switch), they are not listed twice
      if (ev && !money?.market_on) for (const e of ev.events) {
        if (e.date < today || e.date > end || !KINDS.includes(e.kind)) continue;
        out.push({ key: `${e.date}|market|${e.title.toLowerCase()}`, date: e.date, title: e.title, detail: e.detail, to: "/trade/events", tag: "Market", tone: "plain" });
      }
      for (const v of [inRes, usRes]) for (const w of v?.weeks ?? []) for (const r of w.rows) {
        if (r.date < today || r.date > end || r.out) continue;
        out.push({ key: `${r.date}|${r.symbol}|results`, date: r.date, title: `${r.symbol} results`, detail: ["On your watchlist", r.when].filter(Boolean).join(" · "),
          to: `/research/${r.region}/${encodeURIComponent(r.symbol)}`, tag: "Results", tone: "plain" });
      }
      const seen = new Set<string>();
      setRows(out.sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title)).filter((u) => (seen.has(u.key) ? false : (seen.add(u.key), true))).slice(0, limit));
    });
    return () => { live = false; };
  }, [limit]);
  return rows;
}
