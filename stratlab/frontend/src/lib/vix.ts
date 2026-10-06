/* India VIX (Trade): the shapes /trade/vix sends and the few words the panel and the cards share. A published index
 * and arithmetic on it: never what a level means for a trade. */

export type VixQuote = { value: number; prev_close: number | null; change: number | null; change_pct: number | null; open: number | null;
  high: number | null; low: number | null; year_high: number | null; year_low: number | null; as_of: string | null; source: "exchange" | "feed" };
export type VixPercentile = { days: number; need: number; percentile: number | null; low: number | null; high: number | null };
export type Vix = {
  quote: VixQuote | null; value: number | null; intraday: { t: string; v: number }[]; history: { day: string; close: number }[];
  percentile: VixPercentile; stored: { days: number; first: string | null; last: string | null };
  nifty_iv: { today: { iv: number; as_of: string; source: "live" | "recorded" } | null; series: { day: string; iv: number }[] };
  note: string; today: string;
};

export const vixNum = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

/** "+0.57 (+3.94%)" with a real minus sign, or null when there's no previous close. */
export function vixChange(q: VixQuote | null): string | null {
  if (!q || q.change == null) return null;
  const s = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
  return `${s(q.change)}${q.change_pct != null ? ` (${s(q.change_pct)}%)` : ""}`;
}

/** "Higher than 62% of the past year's closes" or why it can't be said yet. */
export function vixPercentileLine(p: VixPercentile): string {
  if (p.percentile == null) return p.days ? `${p.days} days of history; the comparison starts at ${p.need}` : "No history yet";
  return `Higher than ${Math.round(p.percentile)}% of the past year's closes`;
}

/** "5 Oct, 12:04" from an ISO time with an offset, in India time. */
export function vixTime(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
}
