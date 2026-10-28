/* Market Watch's shapes and rules with no page or request in them (MW-1): what a list item is and how an instrument from the
 * search becomes one, how a row is named, sorted and moved, where its chart lives, and how a plan's limit is said before it
 * is met. The panel, the chart page and the unit tests all read this one file. Facts only: names, prices, counts. */
import { LIMITS, PLAN_NAME, type PlanId } from "./plans";

/** An instrument on a list, as the server keeps it: `id` is "MARKET:SYMBOL" (Indian and US stocks by their symbol, indices as
 * "IN:^NSEI", every other market by the markets registry's key: "CRYPTO:BTC-USD", "FX:EURUSD=X", "CMDTY:GC=F"). */
export interface WatchItem { id: string; market: string; symbol: string; name: string; kind: "stock" | "etf" | "index" | "fx" | "crypto" | "commodity" | "future" }
export interface WatchList { id: string; name: string; default: boolean; items: WatchItem[] }
/** What the plan allows, null for no limit; `next` is the plan above that allows more. */
export interface WatchLimits {
  lists: number | null; symbols: number | null; charts: number | null; indicators: number | null;
  next: { lists: string | null; symbols: string | null; charts: string | null; indicators: string | null };
}
export interface WatchQuote { price: number | null; change: number | null; change_pct: number | null; prev_close: number | null; at: string | null; currency: string | null; stale: boolean; delayed?: boolean }

export const DEFAULT_ID = "default";
export type SortMode = "custom" | "change_desc" | "change_asc" | "name";
export const SORTS: { value: SortMode; label: string }[] = [
  { value: "custom", label: "Your order" }, { value: "change_desc", label: "Biggest rise first" },
  { value: "change_asc", label: "Biggest fall first" }, { value: "name", label: "Name" },
];

/** The indices a list can hold, by the symbol the chart and quotes use: the three on the broker's feed and the three US ones. */
export const INDEX_NAME: Record<string, string> = { "^NSEI": "NIFTY 50", "^BSESN": "SENSEX", "^NSEBANK": "NIFTY BANK", "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "DOW JONES" };
const KITE_INDEX_SYMBOL: Record<string, string> = { "NIFTY 50": "^NSEI", "NIFTY BANK": "^NSEBANK", "SENSEX": "^BSESN" };

const item = (market: string, symbol: string, name: string, kind: WatchItem["kind"]): WatchItem => ({ id: `${market}:${symbol}`, market, symbol, name, kind });

/** One tap each on an empty list: the indices, the biggest coins, gold, crude oil and two currency pairs. */
export const POPULAR: WatchItem[] = [
  item("IN", "^NSEI", "NIFTY 50", "index"), item("IN", "^BSESN", "SENSEX", "index"), item("IN", "^NSEBANK", "NIFTY BANK", "index"),
  item("US", "^GSPC", "S&P 500", "index"), item("US", "^IXIC", "NASDAQ", "index"), item("CRYPTO", "BTC-USD", "Bitcoin / US Dollar", "crypto"),
  item("CRYPTO", "ETH-USD", "Ethereum / US Dollar", "crypto"), item("CMDTY", "GC=F", "Gold futures", "commodity"),
  item("CMDTY", "CL=F", "WTI crude oil futures", "commodity"), item("FX", "EURUSD=X", "Euro / US Dollar", "fx"), item("FX", "USDINR=X", "US Dollar / Indian Rupee", "fx"),
];

/** The search's instruments that can go on a list: stocks and ETFs of India and the US, the six indices, and everything the
 * registry carries in the other markets except options (an Indian future or option isn't one: its underlying is). */
export function acceptable(i: { market?: string; type?: string; symbol: string; name?: string; fno?: boolean }): boolean {
  if (i.market === "IN") return i.type === "EQ" || i.type === "ETF" || (i.type === "INDEX" && !!KITE_INDEX_SYMBOL[i.symbol]);
  if (i.market === "US") return i.type === "EQ" || i.type === "ETF";
  return !!i.market && ["UK", "EU", "JP", "FX", "CRYPTO", "MCX", "CDS", "CMDTY"].includes(i.market);
}

const KIND: Record<string, WatchItem["kind"]> = { CRYPTO: "crypto", FX: "fx", CMDTY: "commodity", MCX: "future", CDS: "future" };

/** A search result as a list item (null when it can't be on one). */
export function itemOf(i: { id: string; market?: string; type?: string; symbol: string; name?: string; etf?: boolean; fno?: boolean }): WatchItem | null {
  if (!acceptable(i)) return null;
  const m = i.market!;
  if (m === "IN" || m === "US") {
    if (i.type === "INDEX") return item(m, KITE_INDEX_SYMBOL[i.symbol], INDEX_NAME[KITE_INDEX_SYMBOL[i.symbol]], "index");
    return item(m, i.symbol.toUpperCase(), i.name || i.symbol, i.etf || i.type === "ETF" ? "etf" : "stock");
  }
  const key = i.id.includes(":") ? i.id.slice(i.id.indexOf(":") + 1) : i.symbol;
  return item(m, key.toUpperCase(), i.name || i.symbol, KIND[m] ?? "stock");
}

/** The name a row shows first: the ticker people know. EUR/USD, BTC/USD, NIFTY 50, RELIANCE, Gold. */
export function labelOf(it: WatchItem): string {
  if (it.kind === "index") return INDEX_NAME[it.symbol] ?? it.name;
  if (it.market === "FX") return it.symbol.replace(/=X$/, "").replace(/^(\w{3})(\w{3})$/, "$1/$2");
  if (it.market === "CRYPTO") return it.symbol.replace("-", "/");
  if (it.market === "CMDTY") return (it.name.split(/ futures| \(/)[0] || it.symbol).trim();
  return it.symbol;
}

/** The smaller line under it: the company or pair's name, or where it trades. */
export function subtitleOf(it: WatchItem): string {
  if (it.kind === "index") return it.market === "IN" ? "India index" : "US index";
  const label = labelOf(it);
  const name = it.name && it.name.toUpperCase() !== it.symbol.toUpperCase() ? it.name : "";
  return name && name !== label ? name : (MARKET_NAME[it.market] ?? it.market);
}

export const MARKET_NAME: Record<string, string> = {
  IN: "India", US: "United States", UK: "United Kingdom", EU: "Europe", JP: "Japan", FX: "Forex", CRYPTO: "Crypto", MCX: "Indian commodities",
  CDS: "Indian currency futures", CMDTY: "Global commodities",
};

/** Where an item's chart page is: /chart/IN/RELIANCE, /chart/CRYPTO/BTC-USD. */
export const chartPath = (it: Pick<WatchItem, "market" | "symbol">): string => `/chart/${it.market}/${encodeURIComponent(it.symbol)}`;

/** An item from a chart address (the page opens with only the market and symbol). */
export function itemFromPath(market: string, symbol: string, name?: string): WatchItem {
  const m = market.toUpperCase(), s = decodeURIComponent(symbol).toUpperCase();
  const kind: WatchItem["kind"] = s.startsWith("^") ? "index" : KIND[m] ?? "stock";
  return item(m, s, name || INDEX_NAME[s] || s, kind);
}

/** How the chart reads an item's candles: the company pages' own candles for Indian and US stocks, ETFs and indices, the markets
 * registry's for every other market. `storageKey` is where its drawings are kept (the same on every page that charts it). */
export function chartSource(it: Pick<WatchItem, "market" | "symbol" | "id">): { kind: "company"; region: "IN" | "US"; symbol: string; storageKey: string } | { kind: "instrument"; id: string; storageKey: string } {
  if (it.market === "IN" || it.market === "US") return { kind: "company", region: it.market, symbol: it.symbol, storageKey: `${it.market}:${it.symbol}` };
  return { kind: "instrument", id: it.id, storageKey: it.id };
}

/** The currency an item's prices are in. */
export function currencyOf(it: Pick<WatchItem, "market" | "symbol">): string {
  switch (it.market) {
    case "IN": case "MCX": case "CDS": return "INR";
    case "UK": return "GBP"; case "EU": return "EUR"; case "JP": return "JPY";
    case "CRYPTO": return it.symbol.split("-")[1] ?? "USD";
    case "FX": return it.symbol.replace(/=X$/, "").slice(3, 6) || "USD";
    default: return "USD";
  }
}

/** Markets the broker's feed carries tick by tick (the rest are read every few seconds). */
export const STREAMED = ["IN", "MCX", "CDS"];

/** The day's change of a row: the quote's own figure, or the price against the previous close when only a live price moved. */
export function changeOf(q: WatchQuote | undefined, price?: number | null): number | null {
  if (!q) return null;
  const p = price ?? q.price;
  if (p != null && q.prev_close) return (p / q.prev_close - 1) * 100;
  return q.change_pct;
}

/** Items in the order a sort asks for; "your order" is the list as kept. A row with no change goes last either way. */
export function sortItems(items: WatchItem[], by: SortMode, change: (it: WatchItem) => number | null): WatchItem[] {
  if (by === "custom") return items;
  const out = [...items];
  if (by === "name") return out.sort((a, b) => labelOf(a).localeCompare(labelOf(b)));
  const sign = by === "change_desc" ? -1 : 1;
  return out.sort((a, b) => {
    const x = change(a), y = change(b);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return sign * (x - y);
  });
}

/** An item moved from one place to another. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || from >= items.length) return items;
  const out = [...items];
  const [it] = out.splice(from, 1);
  out.splice(Math.max(0, Math.min(out.length, to)), 0, it);
  return out;
}

/** The name of the next plan up that allows more of a limit than `plan` does (null when none does: Pro has no limit). */
export function nextPlanWith(plan: string, key: "watchlists" | "watchlist_symbols" | "chart_saves" | "chart_indicators"): string | null {
  const order: PlanId[] = ["free", "basic", "pro"];
  const have = LIMITS[plan as PlanId]?.[key];
  if (have === null || have === undefined) return null;
  for (const p of order.slice(order.indexOf(plan as PlanId) + 1)) {
    const n = LIMITS[p][key];
    if (n === null || n > have) return PLAN_NAME[p];
  }
  return null;
}

const have = (plan: string | null, key: "watchlists" | "watchlist_symbols" | "chart_saves" | "chart_indicators"): string => {
  if (!plan) return "";
  const n = LIMITS[plan.toLowerCase() as PlanId]?.[key];
  return n == null ? `${plan} has no limit` : `${plan} keeps ${n}`;
};

/** What the plan keeps and what the next one does, in a sentence, once the list is near its limit or at it; null while there is
 * plenty of room (or no limit). `plan` is the plan's name ("Free"). */
export function symbolsSaid(limits: WatchLimits | null, count: number, plan: string): string | null {
  const cap = limits?.symbols;
  if (!limits || cap == null || count < cap - Math.max(2, Math.floor(cap * 0.15))) return null;
  const more = have(limits.next.symbols, "watchlist_symbols");
  return `${count} of ${cap} symbols on ${plan}.${more ? ` ${more}.` : ""}`;
}

/** The same for the number of lists (shown beside "New list"). */
export function listsSaid(limits: WatchLimits | null, count: number, plan: string): string | null {
  const cap = limits?.lists;
  if (!limits || cap == null || count < cap) return null;
  const more = have(limits.next.lists, "watchlists");
  return `${plan} keeps ${cap} ${cap === 1 ? "list" : "lists"}.${more ? ` ${more}.` : ""}`;
}

/** Indicators on a chart against the plan, said when it is met (the add menu says it instead of adding). */
export function indicatorsSaid(limits: { indicators: number | null; next: { indicators: string | null } } | null, count: number, plan: string): string | null {
  const cap = limits?.indicators;
  if (cap == null || count < cap) return null;
  const more = have(limits!.next.indicators, "chart_indicators");
  return `${plan} keeps ${cap} indicators on a chart.${more ? ` ${more}.` : ""}`;
}

/** Charts that keep drawings against the plan: said before the last one is used (and when it is). */
export function chartsSaid(limit: number | null, count: number, saved: boolean, nextPlan: string | null, plan: string): string | null {
  if (limit == null || saved) return null;
  const more = have(nextPlan, "chart_saves");
  if (count >= limit) return `This chart's drawings and indicators won't be kept: ${plan} keeps ${limit} charts.${more ? ` ${more}.` : ""}`;
  if (count === limit - 1) return `Drawings and indicators are kept on ${count} of ${limit} charts on ${plan}. This is the last one.`;
  return null;
}

export const planName = (plan: string | undefined): string => PLAN_NAME[(plan ?? "free") as PlanId] ?? "Free";

/** A price in the item's own currency, with the decimals its size calls for (forex in 5, crypto by size, the rest in 2). */
export function priceText(v: number | null | undefined, currency: string | null | undefined, market: string, symbol: string): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  const dp = market === "FX" ? (/JPY/.test(symbol) ? 3 : 5) : market === "CDS" ? 4 : a >= 1 ? 2 : a >= 0.01 ? 4 : 8;
  const loc = currency === "INR" ? "en-IN" : "en-US";
  return v.toLocaleString(loc, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

/** +1.23%, −0.40% (a real minus), 0.00% when it rounds to nothing, – with no figure. */
export function changeText(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const t = Math.abs(v).toFixed(2);
  return t === "0.00" ? "0.00%" : `${v > 0 ? "+" : "−"}${t}%`;
}
