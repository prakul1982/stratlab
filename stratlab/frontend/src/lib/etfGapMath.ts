/* The arithmetic and the words of an ETF's gap to its NAV, with no page or request in them (the list's and the badges' shared
 * helpers, and what the unit tests read). */
import type { EtfGap } from "./etfGaps";

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

/** "trades 4.2% above its last NAV". */
export function gapWords(g: number | null | undefined, basis: string): string {
  if (g == null) return "";
  if (Math.abs(g) < 0.005) return `trades at its ${basis}`;
  return `trades ${gapPct(g)} ${g > 0 ? "above" : "below"} its ${basis}`;
}

/** The row as it stands at a price the page already shows (a holding's last price, a company page's quote) instead of
 * the exchange list's own price from its last read: the gap is that price against the iNAV (when a source gave one) or
 * the last NAV, to two places, the list's own arithmetic, so a badge never contradicts the price beside it. A price
 * three or more times the NAV (or under a third of it) is a NAV of another unit, not a real gap (as in the list); a
 * wide gap short of that is real and shown (DF-001: MONQ50 at 86% above). With no usable price, the row stays as the
 * list has it.
 *
 * A NAV is of one day, so the shown price is set against it only when `day` (the price's day) is the NAV's own day;
 * any other price (today's, against yesterday's NAV) would make the day's market move read as a gap (R5O-005), and the
 * row keeps the list's same-day figure (that day's close against that day's NAV). An iNAV moves with the price. */
export function gapAtPrice(r: EtfGap, p: number | null | undefined, day?: string | null): EtfGap {
  if (p == null || !Number.isFinite(p) || p <= 0) return r;
  if (r.inav == null && (!day || day !== r.nav_date)) return r;
  const gapTo = (ref: number | null): number | null => {
    if (ref == null || !(ref > 0)) return null;
    const ratio = p / ref;
    return ratio > 1 / 3 && ratio < 3 ? Math.round((ratio - 1) * 100 * 100) / 100 : null;
  };
  const inav_gap = gapTo(r.inav), nav_gap = gapTo(r.nav);
  const basis = inav_gap != null ? "iNAV" : nav_gap != null ? "NAV" : null;
  const gap = basis === "iNAV" ? inav_gap : nav_gap;
  return { ...r, price: p, price_at: null, inav_gap, nav_gap, gap, basis,
    text: basis ? `${r.symbol} ${gapWords(gap, basis === "iNAV" ? "indicative NAV" : "last NAV")}` : null };
}

/** The gap at the last trade, when that trade is of a later day than the close the list's gap uses: the trade's price against
 * the NAV, both dated by the page beside it ("80.5% above the 23 Oct NAV"). With the market open the first figure a reader
 * sees in a row is the live price, so the row says what it is against too (RC2B-029: ₹213.66 beside an 86.0% that is the
 * 23 Oct close's). It is never the row's gap, which stays one day's close against that day's NAV (R5O-005). Null when the
 * trade is of the close's own day, or the NAV is missing, of a day with no trading, or of another unit. */
export function gapAtLastTrade(r: EtfGap, tradeDay: string | null | undefined): number | null {
  if (!tradeDay || !r.nav_price_day || tradeDay <= r.nav_price_day) return null;
  if (r.nav == null || !(r.nav > 0) || !(r.price > 0) || r.nav_doubtful || r.nav_mismatch || r.nav_closed_day) return null;
  const ratio = r.price / r.nav;
  return ratio > 1 / 3 && ratio < 3 ? Math.round((ratio - 1) * 100 * 100) / 100 : null;
}

/** "14 days", or "13 of 14 days" when a kept day had no gap to count (DF-003: the column said 30 days and never how many). */
export function dayCount(d: { days: number; stored?: number }): string {
  return d.stored && d.stored > d.days ? `${d.days} of ${d.stored} days` : `${d.days} day${d.days === 1 ? "" : "s"}`;
}

/** The gaps of the days shown: how many days had one, the lowest, the highest and the average (the range chosen on the chart, not the
 * stored 30). Null with no gap in them. */
export function gapSummary(days: { day: string; gap: number | null }[]): { days: number; shown: number; low: number; high: number; avg: number; from: string; to: string } | null {
  const g = days.filter((d) => d.gap != null) as { day: string; gap: number }[];
  if (!g.length) return null;
  const sum = g.reduce((a, d) => a + d.gap, 0);
  return { days: g.length, shown: days.length, low: Math.min(...g.map((d) => d.gap)), high: Math.max(...g.map((d) => d.gap)),
    avg: Math.round((sum / g.length) * 100) / 100, from: g[0].day, to: g[g.length - 1].day };
}
