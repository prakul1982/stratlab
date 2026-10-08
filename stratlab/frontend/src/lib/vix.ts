/* India VIX (Trade): the shapes /trade/vix sends and the few words the panel and the cards share. A published index
 * and arithmetic on it: never what a level means for a trade. */
import { asOf, dayIn, fmtDate, IST } from "./format";

export type VixQuote = { value: number; prev_close: number | null; change: number | null; change_pct: number | null; open: number | null;
  high: number | null; low: number | null; year_high: number | null; year_low: number | null; as_of: string | null; source: "exchange" | "feed" };
export type VixPercentile = { days: number; need: number; percentile: number | null; low: number | null; high: number | null };
export type Vix = {
  quote: VixQuote | null; value: number | null; intraday: { t: string; v: number }[]; history: { day: string; close: number }[];
  percentile: VixPercentile; stored: { days: number; first: string | null; last: string | null };
  nifty_iv: { today: { iv: number; as_of: string; source: "live" | "recorded"; at_close?: boolean } | null; series: { day: string; iv: number }[] };
  note: string; today: string;
};

export const vixNum = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));

/** "+0.57 (+3.94%)" with a real minus sign, or null when there's no previous close. */
export function vixChange(q: VixQuote | null): string | null {
  if (!q || q.change == null) return null;
  const s = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
  return `${s(q.change)}${q.change_pct != null ? ` (${s(q.change_pct)}%)` : ""}`;
}

/** How fresh the panel's figures are, and the words its titles use: a quote or a line from an earlier day (in India's
 * date) is never called today's. `asOf` is "5 Oct, 12:04 IST"; `stale` is true when the quote is from before today. */
export function vixFreshness(v: Pick<Vix, "quote" | "intraday" | "today">) {
  const quoteDay = dayIn(v.quote?.as_of, IST);
  const lineDay = v.intraday.length ? dayIn(v.intraday[v.intraday.length - 1].t, IST) : null;
  const name = (d: string) => fmtDate(d, { weekday: true, year: false });
  const stale = !!quoteDay && quoteDay !== v.today;
  const lineStale = !!lineDay && lineDay !== v.today;
  return {
    stale, lineStale, quoteDay, lineDay,
    asOf: asOf(v.quote?.as_of, { tz: IST, year: false }),
    rangeLabel: stale && quoteDay ? `Range on ${name(quoteDay)}` : "Today's range",
    lineTitle: lineStale && lineDay ? name(lineDay) : "Today",
  };
}

/** "Higher than 62% of the past year's closes" or why it can't be said yet. */
export function vixPercentileLine(p: VixPercentile): string {
  if (p.percentile == null) return p.days ? `${p.days} days of history; the comparison starts at ${p.need}` : "No history yet";
  return `Higher than ${Math.round(p.percentile)}% of the past year's closes`;
}
