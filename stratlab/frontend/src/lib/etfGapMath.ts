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
 * the last NAV, to two places, the list's own arithmetic, so a badge never contradicts the price beside it. A gap of
 * more than 50% is a NAV of another unit, not a real gap (as in the list). With no usable price, the row stays as the
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
    const g = (p / ref - 1) * 100;
    return Math.abs(g) <= 50 ? Math.round(g * 100) / 100 : null;
  };
  const inav_gap = gapTo(r.inav), nav_gap = gapTo(r.nav);
  const basis = inav_gap != null ? "iNAV" : nav_gap != null ? "NAV" : null;
  const gap = basis === "iNAV" ? inav_gap : nav_gap;
  return { ...r, price: p, price_at: null, inav_gap, nav_gap, gap, basis,
    text: basis ? `${r.symbol} ${gapWords(gap, basis === "iNAV" ? "indicative NAV" : "last NAV")}` : null };
}
