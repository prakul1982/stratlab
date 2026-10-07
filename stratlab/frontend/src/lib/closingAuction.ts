/* The closing auction desk's data (GET /trade/closing-auction and /history) and the small pure helpers its page uses. */

export type Phase = "none" | "holiday" | "preopen" | "before" | "transition" | "entry" | "matching" | "closed";

export type CasStock = {
  symbol: string; ref: number | null; lower: number | null; upper: number | null; iep: number | null; ieq: number | null;
  final: number | null; final_qty: number | null; price: number | null; final_out: boolean; gap: number | null;
  imbalance: number | null; imbalance_market: number | null; bid: number | null; bid_qty: number | null; ask: number | null;
  ask_qty: number | null; buy_qty: number | null; sell_qty: number | null; text: string | null;
};
export type CasIndex = { name: string; value: number | null; prev_close: number | null; indicative: number | null; status: string | null;
  start: number | null; gap: number | null; close_gap: number | null };
export type CasLeg = { sym: string; side: "buy" | "sell"; opt: "CE" | "PE"; strike: number; qty: number; entry: number; value: number | null; pnl: number | null };
export type CasPosition = { session: string; name: string; underlying: string; settle_on: number | null; basis: string; legs: CasLeg[];
  open_pnl: number | null; closed_pnl: number };
export type Timetable = { since: string; open: string; cas_stocks_continuous_end: string; other_continuous_end: string;
  auction: [string, string] | null; order_entry: [string, string] | null; derivatives_close: string; settlement_fixed_by: string; source: string };
export type CasView = {
  phase: Phase; today: string; trading_day: boolean; timetable: Timetable; day: string | null; fresh: boolean; read: string | null;
  as_of: string | null; from_stored?: boolean; next: { day: string; today: boolean; from: string; to: string } | null; status: string | null; message: string | null; eligible: number; stocks: CasStock[]; indices: CasIndex[];
  expiry: { series: string[]; settlement: string; proposal: string; positions: CasPosition[] };
  history: { allowed: boolean; plan: string; days: number }; sources: Record<string, string>; note: string;
};
export type CasDay = { day: string; stocks: number; avg_abs_gap: number | null; up: number; down: number;
  widest?: { symbol: string; gap: number | null }; indices: { name: string; start: number | null; close: number | null; gap: number | null }[];
  stock?: { ref: number | null; final: number | null; qty: number | null; gap: number | null } | null };
export type CasHistory = { days: CasDay[]; symbol: string | null; note: string };

/** Phases in which the page re-reads every 30 seconds. */
export const LIVE_PHASES: Phase[] = ["before", "transition", "entry", "matching"];

/** The auction's steps on the day's timetable, each with its window and whether it is the current one. */
export function steps(t: Timetable, phase: Phase): { id: Phase; label: string; from: string; to: string; now: boolean }[] {
  if (!t.auction || !t.order_entry) return [];
  return [
    { id: "before", label: "Continuous trading (F&O stocks)", from: t.open, to: t.cas_stocks_continuous_end },
    { id: "transition", label: "Reference price, no orders", from: t.auction[0], to: t.order_entry[0] },
    { id: "entry", label: "Order entry (ends at random in its last 2 minutes)", from: t.order_entry[0], to: t.order_entry[1] },
    { id: "matching", label: "Matching; the final price is the official close", from: t.order_entry[1], to: t.auction[1] },
  ].map((s) => ({ ...s, id: s.id as Phase, now: s.id === phase }));
}

export const PHASE_TEXT: Record<Phase, string> = {
  none: "No closing auction on this day's timetable.",
  holiday: "The market is closed: not a trading day, so no auction today.",
  preopen: "The market is closed until it opens at 09:15. The auction runs from 15:15.",
  before: "Continuous trading. The auction starts at 15:15.",
  transition: "Continuous trading has ended for F&O stocks. The exchange is setting reference prices; orders open at 15:20.",
  entry: "Order entry is open. Indicative prices change until the auction ends.",
  matching: "Order entry has closed. Orders are being matched at each stock's equilibrium price.",
  closed: "The auction is over: final prices are the official closes.",
};

/** "+0.42%" / "−1.10%" / "0.00%", or "–" for none. */
export function gapText(g: number | null | undefined): string {
  if (g == null || !Number.isFinite(g)) return "–";
  if (Math.abs(g) < 0.005) return "0.00%";
  return `${g > 0 ? "+" : "−"}${Math.abs(g).toFixed(2)}%`;
}

/** A quantity as a short Indian number: 1,234 / 12.3 lakh / 1.2 crore. */
export function qtyText(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const a = Math.abs(v), s = v < 0 ? "−" : "";
  if (a >= 1e7) return `${s}${(a / 1e7).toFixed(a >= 1e8 ? 0 : 1)} crore`;
  if (a >= 1e5) return `${s}${(a / 1e5).toFixed(a >= 1e6 ? 0 : 1)} lakh`;
  return `${s}${Math.round(a).toLocaleString("en-IN")}`;
}
