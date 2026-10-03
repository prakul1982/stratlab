/** Stock screens: companies filtered by plain facts, from StratLab's stored company numbers. */
import { api } from "./api";
import type { Region } from "./research";

export type RangeId = "sales_cagr_3y" | "net_margin" | "opm" | "debt_equity" | "roe" | "roce" | "div_yield" | "pe" | "from_high";
export type Bound = { min: number | null; max: number | null };
export interface Filters {
  sector: string[]; cap: string[]; stage: number[]; red_flags: "yes" | "no" | null; ranges: Partial<Record<RangeId, Bound>>;
}
export const NO_FILTERS: Filters = { sector: [], cap: [], stage: [], red_flags: null, ranges: {} };

export interface ScreenMeta {
  region: Region; sectors: string[]; cap: { id: string; label: string }[]; stages: { id: number; label: string }[];
  ranges: { id: RangeId; label: string; unit: "%" | "x"; help: string }[]; help: Record<string, string>;
  red_flags: boolean; columns: string[]; indexed: number; as_of: string | null; index_at: string | null;
}

export interface ScreenRow {
  symbol: string; name: string; sector: string | null; industry: string | null; market_cap: number | null; price: number | null;
  from_high: number | null; sales_cagr_3y: number | null; net_margin: number | null; opm: number | null; debt_equity: number | null;
  roe: number | null; roce: number | null; div_yield: number | null; pe: number | null; stage: number | null; red_flags: number | null;
  price_at: string | null;
}

export interface ScreenResult {
  region: Region; filters: Filters; sort: string; desc: boolean; total: number; offset: number; rows: ScreenRow[];
  indexed: number; as_of: string | null; index_at: string | null;
}

export interface SavedScreen {
  id: string; name: string; region: Region; filters: Filters; sort: string; desc: boolean; notify: boolean;
  created_at: string; last_sent_at: string | null; conditions: string[]; matched_count: number;
}
export interface SavedPage { items: SavedScreen[]; limit: number; count: number; email: string | null; email_confirmed: boolean }

export const screensApi = {
  meta: (r: Region) => api<ScreenMeta>(`/research/screens/meta?region=${r}`),
  run: (r: Region, filters: Filters, sort: string, desc: boolean, offset = 0) =>
    api<ScreenResult>("/research/screens/run", { method: "POST", body: { region: r, filters, sort, desc, offset, limit: 100 } }),
  saved: () => api<SavedPage>("/research/screens/saved"),
  save: (body: { name: string; region: Region; filters: Filters; sort: string; desc: boolean; notify: boolean }, id?: string) =>
    api<SavedPage & { screen: SavedScreen }>(id ? `/research/screens/saved/${id}` : "/research/screens/saved", { method: id ? "PUT" : "POST", body }),
  remove: (id: string) => api<SavedPage>(`/research/screens/saved/${id}`, { method: "DELETE" }),
};

/** How many conditions a screen has, for the filter button's badge. */
export function conditionCount(f: Filters): number {
  return (f.sector.length ? 1 : 0) + (f.cap.length ? 1 : 0) + (f.stage.length ? 1 : 0) + (f.red_flags ? 1 : 0)
    + Object.values(f.ranges).filter((b) => b && (b.min != null || b.max != null)).length;
}
