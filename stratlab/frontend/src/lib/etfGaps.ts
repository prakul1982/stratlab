import { useEffect, useState } from "react";
import { api } from "./api";

/** Indian ETFs' market price against their NAV: the exchange's indicative NAV (iNAV) through market hours and the fund
 * house's last published NAV. One answer for the list page and every badge in the app, read once and kept for five
 * minutes. Facts only: a gap as a percent, with the time of each number. */
export type Fund = "equity" | "gold" | "silver" | "debt" | "intl";
export interface GapSummary { days: number; avg: number; low: number; high: number; from: string; to: string }
export interface EtfGap {
  symbol: string; name: string; underlying: string | null; fund: Fund; fund_label: string;
  price: number; price_at: string | null; inav: number | null; inav_gap: number | null;
  nav: number | null; nav_date: string | null; nav_gap: number | null;
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

/** "4.2%" or "0.35%": one place from 1% up, two below it, without the sign. */
export function gapPct(g: number): string {
  const a = Math.abs(g);
  return `${a >= 1 ? a.toFixed(1) : a.toFixed(2)}%`;
}

/** "4.2% above", "0.35% below", "0.00%" (for a badge or a table cell). */
export function gapShort(g: number | null | undefined): string {
  if (g == null) return "–";
  if (Math.abs(g) < 0.005) return "0.00%";
  return `${gapPct(g)} ${g > 0 ? "above" : "below"}`;
}

/** "trades 4.2% above its iNAV". */
export function gapWords(g: number | null | undefined, basis: string): string {
  if (g == null) return "";
  if (Math.abs(g) < 0.005) return `trades at its ${basis}`;
  return `trades ${gapPct(g)} ${g > 0 ? "above" : "below"} its ${basis}`;
}
