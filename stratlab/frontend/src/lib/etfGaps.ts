import { useEffect, useState } from "react";
import { api } from "./api";

/** Indian ETFs' market price against their NAV: the fund house's last published NAV (with its date), and an indicative
 * NAV (iNAV) only when a source gives one (the exchange's list doesn't). One answer for the list page and every badge in the app, read once and kept for five
 * minutes. Facts only: a gap as a percent, with the time of each number. */
export type Fund = "equity" | "gold" | "silver" | "debt" | "intl";
export interface GapSummary { days: number; avg: number; low: number; high: number; from: string; to: string }
export interface EtfGap {
  symbol: string; name: string; underlying: string | null; fund: Fund; fund_label: string;
  price: number; price_at: string | null; inav: number | null; inav_gap: number | null;
  nav: number | null; nav_date: string | null; nav_gap: number | null;
  /** the price set against the NAV and its day: that day's close (a gap is always of one day), or none yet */
  nav_price?: number | null; nav_price_day?: string | null; nav_waiting?: boolean;
  /** the close and the latest price are too far apart to both be right: the gap is left out (R7O-007) */
  nav_doubtful?: boolean;
  gap: number | null; basis: "iNAV" | "NAV" | null; text: string | null; days?: GapSummary | null;
}
export interface EtfGaps {
  rows: EtfGap[]; as_of: string | null; read: string | null; nav_as_of: string | null; count: number; with_gap: number;
  note: string; alerts: boolean;
}
export interface GapDay { day: string; close: number | null; nav: number | null; gap: number | null }
export interface EtfGapDetail { row: EtfGap; history: GapDay[]; days: GapSummary | null; note: string; alerts: boolean }

export const FUND_NAME: Record<Fund, string> = { equity: "Equity", gold: "Gold", silver: "Silver", debt: "Debt", intl: "International" };

let cached: { at: number; p: Promise<EtfGaps | null> } | null = null;

export function loadEtfGaps(fresh = false): Promise<EtfGaps | null> {
  if (fresh || !cached || Date.now() - cached.at > 5 * 60_000) {
    const p = api<EtfGaps>("/invest/etf-gaps").catch(() => { cached = null; return null; });
    cached = { at: Date.now(), p };
  }
  return cached.p;
}

/** The list, once loaded (null until then, or when it can't be read). `on` false skips the call. */
export function useEtfGaps(on = true): EtfGaps | null {
  const [v, setV] = useState<EtfGaps | null>(null);
  useEffect(() => {
    if (!on) return;
    let live = true;
    loadEtfGaps().then((x) => live && setV(x));
    return () => { live = false; };
  }, [on]);
  return v;
}

export const etfGapApi = {
  detail: (symbol: string) => api<EtfGapDetail>(`/invest/etf-gaps/${encodeURIComponent(symbol)}`),
};

export { gapAtPrice, gapPct, gapShort, gapWords } from "./etfGapMath";
