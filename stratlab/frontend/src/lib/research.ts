import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { currencySymbol } from "./format";

export type Region = "IN" | "US";
export const REGION_NAME: Record<Region, string> = { IN: "India", US: "United States" };
export interface MetricItem { label: string; value: number; unit: "x" | "%" | "%±" | "money" | "cr" }
export interface MetricGroup { title: string; items: MetricItem[] }
export interface NewsItem { headline: string; url: string; source: string; at: string | null }
export interface Quote { price: number | null; change?: number | null; change_pct?: number | null; open?: number | null;
  high?: number | null; low?: number | null; prev_close?: number | null; volume?: number | null }
export interface SourceStatus { source: string; ok: boolean; error: string | null }
export interface SeriesPoint { y: string; v: number }

export interface Company {
  region: Region; symbol: string; name: string; exchange: string | null; currency: string; logo: string | null;
  website: string | null; industry: string | null; facts: { label: string; value: string }[];
  market_cap: number | null; quote: Quote | null; range52: { low: number | null; high: number | null };
  margins: { gross: number | null; operating: number | null; net: number | null } | null;
  metrics: MetricGroup[];
  trend: { unit: string; revenue: SeriesPoint[]; profit: SeriesPoint[]; revenue_label: string; profit_label: string } | null;
  quarters?: { cols: string[]; sales: (number | null)[]; profit: (number | null)[]; opm: (number | null)[] } | null;
  shareholding?: { as_of: string; rows: { label: string; value: number; change: number | null }[] } | null;
  pros?: string[]; cons?: string[];
  earnings: { period: string; actual: number; estimate: number; surprise_pct: number }[];
  next_earnings: { date: string; eps_estimate: number | null } | null;
  analysts: { strongBuy: number; buy: number; hold: number; sell: number; strongSell: number; period: string } | null;
  insider: { net: number; rows: { name: string; change: number; date: string }[] } | null;
  peers: string[]; news: NewsItem[];
  about: { wiki: { title: string; description?: string; extract: string; url: string } | null; profile: string | null };
  sources: SourceStatus[]; links: { label: string; url: string }[];
  testable: boolean; instrument_id: string | null;
}

export interface Idea { title: string; text: string; why: string }
export interface CompanyAI {
  summary: string; scores: Record<"moat" | "growth" | "value" | "momentum" | "health", number | null>;
  composite: number | null; valuation: "CHEAP" | "FAIR" | "RICH" | null; valuation_note: string;
  bull: string[]; bear: string[]; segments: { label: string; share: number }[]; position: string; watch: string[];
  ideas: Idea[]; generated_at: number;
}
export interface Co { name: string; ticker: string }
export interface SectorAI {
  sector: string; summary: string; market_size: string; cagr: number | null; cagr_note: string;
  etfs: { ticker: string; name: string }[]; sub_themes: { name: string; detail: string }[]; core: string;
  clusters: { name: string; companies: Co[] }[];
  screen: { name: string; ticker: string; layer: string; composite: number | null; one_line: string }[];
  value_chain: { layer: string; description: string; companies: Co[] }[];
  tailwinds: string[]; risks: string[]; generated_at: number;
}
export interface IndexLevel { name: string; price: number; change_pct: number | null; high52: number | null; from_high_pct: number | null }
export interface PulseAI {
  tone: string; hot: { name: string; ticker: string; why: string }[];
  flows: { title: string; detail: string; direction: "INFLOW" | "OUTFLOW" | "ROTATION" }[];
  themes: { theme: string; detail: string; example: string }[]; generated_at: number;
}
export interface CompareAI {
  verdict: string; winner: string; differences: string[];
  a: { composite: number | null; valuation: string | null }; b: { composite: number | null; valuation: string | null };
  generated_at?: number; error?: string;
}
export interface WatchItem { region: Region; symbol: string; name: string | null }

export const researchApi = {
  company: (r: Region, s: string) => api<Company>(`/research/company/${r}/${encodeURIComponent(s)}`),
  companyAI: (r: Region, s: string, refresh = false) => api<CompanyAI>(`/research/company/${r}/${encodeURIComponent(s)}/ai${refresh ? "?refresh=true" : ""}`),
  chart: (r: Region, s: string, range: string) =>
    api<{ currency: string; source: string; candles: { t: string; c: number }[] }>(`/research/chart/${r}/${encodeURIComponent(s)}?range=${range}`),
  quotes: (r: Region, syms: string[]) => api<Record<string, Quote | null>>(`/research/quotes?region=${r}&symbols=${syms.map(encodeURIComponent).join(",")}`),
  search: (r: Region, q: string) => api<{ symbol: string; name: string; exchange: string; region: Region }[]>(`/research/search?region=${r}&q=${encodeURIComponent(q)}`),
  pulse: (r: Region, focus = "") => api<{ indices: IndexLevel[]; headlines: NewsItem[] }>(`/research/pulse?region=${r}&focus=${encodeURIComponent(focus)}`),
  pulseAI: (r: Region, focus = "", refresh = false) => api<PulseAI>(`/research/pulse/ai?region=${r}&focus=${encodeURIComponent(focus)}${refresh ? "&refresh=true" : ""}`),
  sector: (r: Region, q: string, refresh = false) => api<SectorAI>(`/research/sector?region=${r}&q=${encodeURIComponent(q)}${refresh ? "&refresh=true" : ""}`),
  compare: (r: Region, a: string, b: string) => api<{ a: Company; b: Company; ai: CompareAI }>(`/research/compare?region=${r}&a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
};

/* ---------- region preference ---------- */
export function savedRegion(): Region {
  try { return (localStorage.getItem("stratlab.research.region") as Region) === "US" ? "US" : "IN"; } catch { return "IN"; }
}
export function saveRegion(r: Region) {
  try { localStorage.setItem("stratlab.research.region", r); } catch { /* private window */ }
}

/* ---------- watchlist, shared across pages ---------- */
let watchCache: WatchItem[] | null = null;
const watchSubs = new Set<(w: WatchItem[]) => void>();

export function useWatchlist() {
  const [items, setItems] = useState<WatchItem[] | null>(watchCache);
  useEffect(() => {
    watchSubs.add(setItems);
    if (!watchCache) api<{ items: WatchItem[] }>("/research/watchlist").then((r) => { watchCache = r.items; watchSubs.forEach((f) => f(r.items)); }).catch(() => {});
    return () => { watchSubs.delete(setItems); };
  }, []);
  const save = useCallback(async (next: WatchItem[]) => {
    const prev = watchCache;
    watchCache = next; watchSubs.forEach((f) => f(next));
    try { await api("/research/watchlist", { method: "PUT", body: { items: next } }); }
    catch (e) { watchCache = prev; watchSubs.forEach((f) => f(prev ?? [])); throw e; }
  }, []);
  const has = (r: Region, s: string) => !!items?.some((i) => i.region === r && i.symbol === s);
  const toggle = (item: WatchItem) => save(has(item.region, item.symbol)
    ? (items ?? []).filter((i) => !(i.region === item.region && i.symbol === item.symbol))
    : [...(items ?? []), item]);
  return { items, has, toggle, save };
}

/* ---------- formatting ---------- */
/** Big money: $4.31T, $12.4B, ₹19.05L Cr, ₹8,500 Cr. */
export function bigMoney(v: number | null | undefined, currency: string): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const s = currencySymbol(currency);
  if (currency === "INR") {
    const cr = v / 1e7;
    return cr >= 1e5 ? `${s}${(cr / 1e5).toFixed(2)}L Cr` : `${s}${Math.round(cr).toLocaleString("en-IN")} Cr`;
  }
  const a = Math.abs(v);
  if (a >= 1e12) return `${s}${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${s}${(v / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${s}${(v / 1e6).toFixed(0)}M`;
  return `${s}${Math.round(v).toLocaleString()}`;
}

/** A trend value in its unit: "₹ Cr" values are already crores, "USD" values are dollars. */
export function trendValue(v: number, unit: string): string {
  // Indian figures are in crore: show them whole (₹2,812 Cr), with a decimal only for small ones (₹4.6 Cr)
  if (/cr/i.test(unit)) {
    const a = Math.abs(v);
    return a < 10 ? v.toFixed(1) : Math.round(v).toLocaleString("en-IN");
  }
  const a = Math.abs(v);      // other markets report in whole currency units
  return a >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.round(v).toLocaleString("en-US");
}

export function metricText(m: MetricItem, currency: string): string {
  const v = m.value;
  if (m.unit === "%") return `${v.toFixed(1)}%`;
  if (m.unit === "%±") return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;
  if (m.unit === "money") return `${currencySymbol(currency)}${v.toLocaleString(currency === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: 2 })}`;
  if (m.unit === "cr") return `₹${Math.round(v).toLocaleString("en-IN")} Cr`;
  return v.toFixed(Math.abs(v) >= 100 ? 0 : 2);
}

/* ---------- where a number sits in a typical range (from Hindsight) ----------
 * [floor, weak edge, strong edge, ceiling, higher-is-better]. Loose large-cap defaults,
 * widened or narrowed for industries where the normal range is different. */
type Band = [number, number, number, number, boolean];
const BANDS: Record<string, Band> = {
  "P/E": [0, 12, 30, 70, false], "Fwd P/E": [0, 10, 26, 60, false], "P/S": [0, 1.5, 6, 20, false], "P/B": [0, 1.5, 6, 50, false],
  "EV/EBITDA": [0, 7, 18, 45, false], "EV/FCF": [0, 12, 30, 70, false], "PEG (fwd)": [0, 1, 2.5, 5, false],
  "Gross margin": [0, 25, 45, 90, true], "Operating margin": [-10, 8, 22, 55, true], "Net margin": [-10, 5, 18, 45, true],
  "OPM": [-10, 8, 22, 55, true], "ROE": [-10, 8, 20, 60, true], "ROA": [-5, 3, 10, 35, true], "ROCE": [-5, 8, 20, 50, true],
  "Revenue YoY": [-25, 0, 10, 45, true], "EPS YoY": [-40, 0, 12, 70, true], "Revenue 3Y": [-15, 0, 8, 35, true],
  "Revenue 5Y": [-15, 0, 8, 35, true], "EPS 5Y": [-25, 0, 10, 45, true], "Latest YoY": [-25, 0, 10, 45, true],
  "3Y CAGR": [-15, 0, 10, 35, true], "5Y CAGR": [-15, 0, 10, 35, true], "10Y CAGR": [-10, 0, 10, 30, true],
  "Current ratio": [0, 1, 2, 4, true], "LT debt / equity": [0, 0.5, 1.5, 3, false], "Debt / equity": [0, 0.5, 1.5, 3, false],
  "Interest coverage": [0, 3, 10, 30, true], "Asset turnover": [0, 0.4, 1, 2.5, true], "Beta": [0, 0.8, 1.4, 2.5, false],
  "1Y return": [-50, 0, 15, 90, true], "Div yield": [0, 0.5, 2.5, 7, true], "Payout ratio": [0, 20, 70, 120, false],
};
const SCALE: Record<string, Record<string, number>> = {
  software: { "P/S": 2.2, "P/B": 2, "P/E": 1.4 }, technology: { "P/S": 1.8, "P/B": 1.8, "P/E": 1.3 },
  semiconductors: { "P/S": 2, "P/B": 1.8, "P/E": 1.3 }, biotechnology: { "P/S": 3, "P/E": 2 },
  bank: { "P/B": 0.4, "P/S": 0.5, "Gross margin": 0.6 }, insurance: { "P/B": 0.5, "P/S": 0.4 },
  "real estate": { "P/B": 0.6, "LT debt / equity": 2 }, utilities: { "LT debt / equity": 2, "Revenue YoY": 0.5 },
  retail: { "Gross margin": 0.6, "Net margin": 0.5, "P/S": 0.4 }, energy: { "Revenue YoY": 1.6, "P/E": 0.7 },
  automobiles: { "Gross margin": 0.5, "Net margin": 0.5, "P/S": 0.5 },
};

export function bandPosition(label: string, value: number, industry?: string | null): { pos: number; weak: number; strong: number; tone: "good" | "bad" | "mid" } | null {
  const b = BANDS[label];
  if (!b) return null;
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
