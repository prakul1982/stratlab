import { api } from "./api";
import type { Region } from "./research";

/* The theme deep dive (THEME-1): every figure is from the app's stored company facts, the AI writes none of them. These are the shapes the
 * server sends (backend/app/intel/theme_data.py, theme_prices.py, theme_routes.py) and the few plain helpers the tables share. */

export interface Stat { n: number; median: number; min: number; max: number }
export interface YearRow { year: string; sales: number | null; profit: number | null; opm: number | null }
export interface DiveRow {
  symbol: string; name: string; year: string | null; unit: string | null; bank: boolean; revenue: number | null; profit: number | null;
  ebitda: number | null; net: number | null; roce: number | null; cap: number | null; pe: number | null; debt_equity: number | null;
  sales_1y: number | null; sales_3y: number | null; profit_1y: number | null; stage: number | null; from_high: number | null;
  pb: number | null; interest_cover: number | null; ev_ebitda: number | null; quarter: { of: string; sales: number | null; profit: number | null } | null;
  what?: string | null; company_wide?: boolean; years?: YearRow[];
}
export interface BizRow {
  symbol: string; name: string; metric: string; unit: string | null; span: "month" | "quarter"; period: string; value: number; prev: number | null; year_ago: number | null;
  change_prev: number | null; change_year: number | null; filed: string; url: string | null; page: number | null; exchange: string | null;
  points: { period: string; value: number }[];
}
export interface History { years: string[]; ebitda: (number | null)[]; net: (number | null)[]; n: number; companies: string[] }
export interface Layer {
  layer: string; description: string; companies: DiveRow[]; n: number; revenue: number | null; line: string | null; history: History | null;
  stats: { ebitda: Stat | null; net: Stat | null; roce: Stat | null }; company_wide: string[]; left_out: number; stats_over: "own" | "all";
}
export interface ChainRow { layer: string; n: number; revenue: number | null; ebitda: number | null; net: number | null; roce: number | null; ebitda_n: number }
export interface SubCompany { symbol: string; name: string; what: string | null; cap: number | null; sales_1y: number | null; ebitda: number | null; company_wide: boolean; year: string | null }
export interface Holding { symbol: string; name: string; quarter: string; promoter: number | null; institutions: number | null; promoter_change: number | null; institutions_change: number | null }
export interface Flag { symbol: string; name: string; at: string; label: string; severity?: string; subject?: string; url?: string | null }
export interface Dive {
  region: Region; sector: string; as_of: string | null; unit: string | null; basis: string; members: number; company_wide: string[];
  layers: Layer[]; chain: { rows: ChainRow[]; line: string | null; highest: string | null; lowest: string | null };
  subs: { name: string; detail: string; companies: SubCompany[] }[];
  placements?: { checked: boolean; pending: number; left_out: number; placed: number; unconfirmed?: number } | null;
  notable: { kind: "gap" | "move" }[];
  sections: {
    size: { companies: number; with_value: number; total_cap: number | null; biggest: { symbol: string; name: string; cap: number; share: number }[]; top3_share: number | null };
    medians: Record<"ebitda" | "net" | "roce", Stat | null>;
    growth: { aggregate: Record<string, { value: number; n: number; year: string }>; median: Record<string, Stat> };
    margins: History | null;
    valuation: { pe: Stat | null; market_pe: Stat | null; market_n: number; pb: Stat | null; market_pb: Stat | null; ev_ebitda: Stat | null; ev_missing: number; history: { d: string; pe: number; n: number }[] };
    quarter: { companies: { symbol: string; name: string; of: string; sales: number | null; profit: number | null }[]; sales_up: number; sales_down: number; profit_up: number; profit_down: number; sales: Stat | null; profit: Stat | null };
    balance: { debt_equity: Stat | null; above_1: number; with_debt_equity: number; cfo_to_profit: Stat | null; cfo_n: number; interest_cover: Stat | null; cover_under_2: number };
    price: Record<"stage2" | "supertrend_up" | "near_high" | "near_low", { n: number; count: number; share: number | null }>;
    market: Record<string, Stat | null>;
    ownership: { holdings: Holding[]; promoter_up: number; promoter_down: number; promoter_median: Stat | null; insider_buys: { symbol: string; name: string; at: string }[]; pledges: Flag[]; red_flags: Flag[] };
    events: { results_due: { symbol: string; name: string; date: string; purpose: string | null }[];
      results_filed: { symbol: string; name: string; date: string; numbers: { label: string; value: string }[]; url: string | null }[];
      actions: { symbol: string; name: string; date: string; kind: string; label: string; text: string }[] };
    management: { companies: { symbol: string; name: string; met: number; missed: number }[]; met: number; missed: number; with_card: number };
    leaders: DiveRow[];
  };
}
export interface PriceRow { symbol: string; name: string; ret: Record<"1M" | "3M" | "1Y" | "3Y", number | null>; date: string; above200: boolean | null; near_high: boolean | null; near_low: boolean | null }
export interface Prices {
  companies: PriceRow[]; median: Record<string, { median: number; n: number } | null>; pending: number; benchmark: string; as_of: string | null;
  above200: { n: number; count: number; share: number | null }; near_high: { n: number; count: number; share: number | null }; near_low: { n: number; count: number; share: number | null };
  line: { weeks: string[]; theme: number[]; bench: number[]; rs: number[] } | null;
  returns: Record<string, { theme: number | null; bench: number | null }> | null;
}
export interface NewsRow { at: string; headline: string; company: string | null; symbol: string | null; source: string; url: string; kind: "news" | "filing" }
export interface Listing { id: string; name: string; symbol: string | null; stage: string; industry: string | null; open: string | null; close: string | null; listing: string | null; groups: string[]; what: string }
export interface Business { allowed: boolean; layers: { layer: string; rows: BizRow[] }[]; subs: { name: string; rows: BizRow[] }[]; companies: number; of: number }

const q = (r: Region, theme: string) => `region=${r}&q=${encodeURIComponent(theme)}`;
export const themeApi = {
  dive: (r: Region, theme: string, refresh = false) => api<Dive>(`/research/theme-dive?${q(r, theme)}${refresh ? "&refresh=true" : ""}`),
  prices: (r: Region, theme: string) => api<Prices>(`/research/theme-dive/prices?${q(r, theme)}`),
  news: (r: Region, theme: string) => api<{ items: NewsRow[]; as_of: string }>(`/research/theme-dive/news?${q(r, theme)}`),
  listings: (r: Region, theme: string) => api<{ items: Listing[]; checked: boolean }>(`/research/theme-dive/listings?${q(r, theme)}`),
  business: (r: Region, theme: string) => api<Business>(`/research/theme-dive/business?${q(r, theme)}`),
  draft: (r: Region, theme: string) => api<{ result: string; slug: string | null; problem?: string }>("/admin/blog/theme", { method: "POST", body: { q: theme, region: r } }),
};

export { amount, pc, times, points, span, layerLines, type LayerLine } from "./themeFormat";
