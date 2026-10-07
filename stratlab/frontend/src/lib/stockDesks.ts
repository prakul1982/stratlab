import { api } from "./api";
import { fmtDate } from "./format";

/** The per-stock market desks' answers: stock futures (/trade/stock-futures), stock lending fees
 * (/invest/stock-lending) and margin-funded positions (/invest/margin-funding). Facts and arithmetic only. */

export type DeskStatus = { status: "ok" | "pending" | "none"; as_of: string | null; expected: string | null; days: number; first: string | null;
  reason: string | null; backfill_done: boolean; backfill_target: number };

export type Buildup = "LB" | "SB" | "SC" | "LU";
export type FutRow = {
  symbol: string; px: number | null; pc: number | null; oi: number | null; oc: number | null; b: Buildup | null;
  n: number | null; x: number | null; f: number | null; e: string | null; td: number | null; r: number | null; s: number | null;
  bp: number | null; ba: number | null; be: string | null; vol: number | null; lot: number | null; m: number | null; mwpl?: number | null;
  feq?: number | null; ban_next: boolean; ban_now: boolean; roll_window: boolean; streak: number | null; as_of?: string;
};
export type FutTable = { status: DeskStatus; rows: FutRow[]; as_of: string | null; prev: string | null; labels: Record<Buildup, string>;
  about: Record<string, string>; note: string; source: string; ban_at: number; free_at: number; watch_at: number; roll_window: number;
  full: boolean; plan_needed: string; mwpl_file?: boolean };
export type FutPoint = { day: string; px: number | null; pc: number | null; oi: number | null; oc: number | null; b: Buildup | null;
  r: number | null; ba: number | null; m: number | null; s: number | null };
export type FutDetail = { row: FutRow; full: boolean; history: FutPoint[] | null; range: string; labels: Record<Buildup, string>;
  plan_needed: string; note: string; about: Record<string, string>; stored?: number };

export type LendSummary = { days: number; traded_days: number; shares: number; lines: number; fee_paid: number; ann_low: number | null;
  ann_high: number | null; ann_avg: number | null; last: { day: string; series: string; expiry: string; fee: number | null; ann: number | null } | null };
export type LendTrade = { day: string; price: number | null; series: string; expiry: string; fee: number | null; ann: number | null; shares: number; trades: number };
export type LendRow = { symbol: string; eligible: boolean | null; eligible_as_of: string | null; as_of: string | null; summaries: LendSummary[];
  trades?: LendTrade[]; held?: boolean; watched?: boolean };
export type LendTable = { rows: LendRow[]; status: DeskStatus; note: string; source: string; facts: { title: string; text: string }[];
  windows: number[]; coverage: { days: number; first: string | null } };

export type MtfChange = { from: string; shares: number; crore: number; pct: number | null } | null;
export type MtfRow = { symbol: string; as_of: string | null; funded: boolean; shares?: number; crore?: number; close?: number | null;
  issued?: number | null; pct_shares?: number | null; pct_mcap?: number | null; day?: MtfChange; d30?: MtfChange; d90?: MtfChange;
  history?: { day: string; shares: number; crore: number; close: number | null; pct_shares: number | null }[]; held?: boolean; watched?: boolean };
export type MtfMarket = { as_of: string | null; end?: number | null; start?: number | null; fresh?: number | null; liquidated?: number | null;
  stocks?: number; d30?: { from: string; crore: number; pct: number }; history?: { day: string; end: number; fresh: number | null; liquidated: number | null }[] };
export type MtfPage = { market: MtfMarket; rows: MtfRow[]; status: DeskStatus; full: boolean; about: Record<string, string>; shares_as_of: string | null;
  note: string; source: string; plan_needed: string };
export type MtfOne = MtfRow & { full: boolean; status: DeskStatus; about: Record<string, string>; note: string; plan_needed: string };
export type CostIn = { buy: number; qty: number; margin_pct: number; rate_pct: number; days: number; charges: number; price: number | null; maint_pct: number };
export type CostOut = { value: number; funded: number; own: number; interest: number; interest_day: number; costs: number; breakeven: number;
  breakeven_pct: number; cost_pct_own: number | null; breach_price?: number; breach_fall_pct?: number; breach_from?: number; price?: number;
  now_value?: number; margin_now_pct?: number; pnl?: number; pnl_pct_own?: number | null };

export const desksApi = {
  futures: () => api<FutTable>("/trade/stock-futures"),
  future: (s: string, range = "6m") => api<FutDetail>(`/trade/stock-futures/${encodeURIComponent(s)}?range=${range}`),
  lending: () => api<LendTable>("/invest/stock-lending"),
  lend: (s: string) => api<LendRow & { status: DeskStatus; note: string }>(`/invest/stock-lending/${encodeURIComponent(s)}`),
  mtf: () => api<MtfPage>("/invest/margin-funding"),
  mtfOne: (s: string, range = "1y") => api<MtfOne>(`/invest/margin-funding/${encodeURIComponent(s)}?range=${range}`),
  cost: (b: CostIn) => api<CostOut>("/invest/margin-funding/cost", { method: "POST", body: b }),
};

/** "+1.23%" / "−0.40%" with a real minus sign; "–" when missing. */
export const signedPct = (v: number | null | undefined, dp = 2) =>
  v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(dp)}%`;
export const plainPct = (v: number | null | undefined, dp = 1) => (v == null ? "–" : `${v.toFixed(dp)}%`);
/** Shares in Indian grouping, or in lakh/crore when large: "1.46 cr", "8.1 lakh". */
export function sharesShort(v: number | null | undefined): string {
  if (v == null) return "–";
  const a = Math.abs(v);
  if (a >= 1e7) return `${(v / 1e7).toFixed(2)} cr`;
  if (a >= 1e5) return `${(v / 1e5).toFixed(1)} lakh`;
  return Math.round(v).toLocaleString("en-IN");
}
export const rupees = (v: number | null | undefined, dp = 2) =>
  v == null ? "–" : `${v < 0 ? "−" : ""}₹${Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
export const dayText = (iso: string | null | undefined) =>
  !iso ? "–" : fmtDate(iso.slice(0, 10));
export const dayShort = (iso: string) => fmtDate(iso.slice(0, 10), { year: false });

/** The status line under a desk's title: the newest day, or why it isn't there. */
export function statusText(s: DeskStatus | undefined, what: string): string {
  if (!s) return "";
  if (!s.as_of) return s.reason ?? `No ${what} yet.`;
  const head = `${what[0].toUpperCase()}${what.slice(1)} of ${dayText(s.as_of)} · ${s.days} trading day${s.days === 1 ? "" : "s"} of history`;
  return s.status === "ok" || !s.reason ? head : `${head}. ${s.reason}`;
}
