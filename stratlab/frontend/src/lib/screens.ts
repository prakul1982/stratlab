/** Stock screens: companies filtered by plain facts, from StratLab's stored company numbers. */
import { api } from "./api";
import type { Region } from "./research";
import { track } from "./analytics";

export type RangeId = "sales_cagr_3y" | "net_margin" | "opm" | "debt_equity" | "roe" | "roce" | "div_yield" | "pe" | "from_high";
export type Bound = { min: number | null; max: number | null };
export interface Filters {
  sector: string[]; cap: string[]; stage: number[]; red_flags: "yes" | "no" | null; ranges: Partial<Record<RangeId, Bound>>;
  /** a promoter or insider bought on the open market in the last `insider_days` days (India) */
  insider_buy?: "yes" | "no" | null; insider_days?: number;
  /** on (or not on) one of the exchange surveillance lists in `surv_lists`, or any list when it is empty (India) */
  surveillance?: "on" | "off" | null; surv_lists?: string[];
}
export const NO_FILTERS: Filters = {
  sector: [], cap: [], stage: [], red_flags: null, insider_buy: null, insider_days: 90, surveillance: null, surv_lists: [], ranges: {},
};

export interface ScreenMeta {
  region: Region; sectors: string[]; cap: { id: string; label: string }[]; stages: { id: number; label: string }[];
  ranges: { id: RangeId; label: string; unit: "%" | "x"; help: string }[]; help: Record<string, string>;
  red_flags: boolean; columns: string[]; indexed: number; as_of: string | null; index_at: string | null;
  insider: { days: number[]; default: number; from: string | null } | null;
  surveillance?: { lists: { id: string; label: string }[] } | null;
}

export interface ScreenRow {
  symbol: string; name: string; sector: string | null; industry: string | null; market_cap: number | null; price: number | null;
  from_high: number | null; sales_cagr_3y: number | null; net_margin: number | null; opm: number | null; debt_equity: number | null;
  roe: number | null; roce: number | null; div_yield: number | null; pe: number | null; stage: number | null; red_flags: number | null;
  price_at: string | null;
  /** the stock's exchange surveillance flags today (India) */
  surveillance?: string[];
}

export interface ScreenResult {
  region: Region; filters: Filters; sort: string; desc: boolean; total: number; offset: number; rows: ScreenRow[];
  indexed: number; as_of: string | null; index_at: string | null;
  /** the newest price day among the rows shown; `as_of` is the oldest, so the header never claims a newer close (R7O-004) */
  as_of_newest?: string | null;
}

export interface SavedScreen {
  id: string; name: string; region: Region; filters: Filters; sort: string; desc: boolean; notify: boolean;
  created_at: string; last_sent_at: string | null; conditions: string[]; matched_count: number;
}
export interface SavedPage { items: SavedScreen[]; limit: number; count: number; email: string | null; email_confirmed: boolean }

export const screensApi = {
  meta: (r: Region) => api<ScreenMeta>(`/research/screens/meta?region=${r}`),
  run: (r: Region, filters: Filters, sort: string, desc: boolean, offset = 0) =>
    api<ScreenResult>("/research/screens/run", { method: "POST", body: { region: r, filters, sort, desc, offset, limit: 100 } })
      .then((out) => { if (!offset) track("screen run", { region: r, filters: conditionCount(filters) }); return out; }),
  saved: () => api<SavedPage>("/research/screens/saved"),
  save: (body: { name: string; region: Region; filters: Filters; sort: string; desc: boolean; notify: boolean }, id?: string) =>
    api<SavedPage & { screen: SavedScreen }>(id ? `/research/screens/saved/${id}` : "/research/screens/saved", { method: id ? "PUT" : "POST", body })
      .then((out) => { if (!id) track("screen saved", { region: body.region, filters: conditionCount(body.filters) }); return out; }),
  remove: (id: string) => api<SavedPage>(`/research/screens/saved/${id}`, { method: "DELETE" }),
};

/** How many conditions a screen has, for the filter button's badge. */
export function conditionCount(f: Filters): number {
  return (f.sector.length ? 1 : 0) + (f.cap.length ? 1 : 0) + (f.stage.length ? 1 : 0) + (f.red_flags ? 1 : 0) + (f.insider_buy ? 1 : 0) + (f.surveillance ? 1 : 0)
    + Object.values(f.ranges).filter((b) => b && (b.min != null || b.max != null)).length;
}
