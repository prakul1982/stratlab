/* Formatting for the research pages that needs no browser: the unit a group of amounts reads in, trend values,
 * metric figures, and the market read's focus parameter. Re-exported by research.ts. */
import { CRORE, inrCompact, minus, currencySymbol } from "./format";
import type { MetricItem } from "./research";

/** "&focus=..." for a focus that was typed; nothing for none (an empty parameter is no focus). */
export function focusParam(focus: string): string {
  const f = focus.trim();
  return f ? `&focus=${encodeURIComponent(f)}` : "";
}

/** The currency a US filing's amounts are in: "$", or a foreign filer's own ("CAD million" → "CAD"). */
export function millionsOf(unit: string | null | undefined): string {
  const m = /^([A-Z]{3}) million$/.exec(unit ?? "");
  return m ? m[1] : "$";
}

/** The unit a group of amounts (one chart, one table) reads best in. US filings are in $ million and Indian figures in
 * ₹ crore; a group switches to $ billion or ₹ lakh crore only when it's large AND every number in it still shows to
 * within 1% (so a small loss is never printed as 0.00). Only the display unit changes, never the amount. `unit`: a
 * US-listed foreign filer's own ("CAD million"), labelled "CAD million" / "CAD billion". */
export type Scale = { k: number; unit: string; fmt: (x: number | null | undefined) => string };
export function scaleFor(values: (number | null | undefined)[], us: boolean, unit?: string | null): Scale {
  const nz = values.filter((x): x is number => x != null && Number.isFinite(x) && x !== 0).map(Math.abs);
  const max = nz.length ? Math.max(...nz) : 0, min = nz.length ? Math.min(...nz) : 0;
  const make = (k: number, unit: string, dp: number, locale: string): Scale =>
    ({ k, unit, fmt: (x) => (x == null ? "–" : minus((x / k).toLocaleString(locale, { minimumFractionDigits: dp, maximumFractionDigits: dp }))) });
  if (us) {
    const cur = millionsOf(unit);
    if (max >= 10000 && min >= 5000) return make(1000, `${cur} billion`, 1, "en-US");
    if (max >= 10000 && min >= 500) return make(1000, `${cur} billion`, 2, "en-US");
    return { k: 1, unit: `${cur} million`, fmt: (x) => (x == null ? "–" : minus(x.toLocaleString("en-US", { maximumFractionDigits: 2 }))) };
  }
  if (max >= 100000 && min >= 50000) return make(100000, "₹ lakh cr", 2, "en-IN");
  return { k: 1, unit: "₹ cr", fmt: (x) => (x == null ? "–" : minus(x.toLocaleString("en-IN", { maximumFractionDigits: 2 }))) };
}

/** A trend value in its unit: "₹ Cr" values are already crores, "USD" values are dollars. */
export function trendValue(v: number, unit: string): string {
  // Indian figures are in crore: show them whole (₹2,812 Cr), with a decimal only for small ones (₹4.6 Cr)
  if (/billion/i.test(unit)) return minus(v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: Math.abs(v) < 10 ? 2 : 1 }));
  if (/lakh/i.test(unit)) return minus(v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  if (/cr/i.test(unit)) {
    const a = Math.abs(v);
    return a < 10 ? minus(v.toFixed(1)) : minus(Math.round(v).toLocaleString("en-IN"));
  }
  const a = Math.abs(v);      // other markets report in whole currency units
  return minus(a >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : Math.round(v).toLocaleString("en-US"));
}

export function metricText(m: MetricItem, currency: string): string {
  const v = m.value;
  // a percentage that isn't zero never reads as "0.0%": a tiny one keeps two decimals (a 0.01% net margin)
  // a figure the source gives in whole numbers (its growth rates: "-12%") is shown whole, never as a precise "-12.0%"
  const dp = m.dp ?? (v !== 0 && Math.abs(v) < 0.05 ? 2 : 1);
  if (m.unit === "%") return minus(`${v.toFixed(dp)}%`);
  if (m.unit === "%±") return `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(dp)}%`;
  if (m.unit === "money") return `${currencySymbol(currency)}${v.toLocaleString(currency === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: 2 })}`;
  if (m.unit === "cr") return inrCompact(v * CRORE);        // the figure is in crore: ₹925 cr, ₹1.51 lakh cr
  return minus(v.toFixed(Math.abs(v) >= 100 ? 0 : 2));
}


/* ---------- how old a reported period or a headline is ---------- */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** The last day of a period labelled like "Jun 2025" (a quarter or a year to that month); null for another label. */
export function periodEnd(label: string): Date | null {
  const m = /^([A-Z][a-z]{2})\s+(\d{4})$/.exec(String(label).trim());
  const i = m ? MONTHS.indexOf(m[1]) : -1;
  return i < 0 ? null : new Date(Date.UTC(Number(m![2]), i + 1, 0));
}

/** How many whole months old a quarter's figures are, when a newer quarter's should be out by now (companies file
 * results within 45 days of a quarter's end, 60 for the year's last; shareholding within 21): `lagDays` after the end
 * of a later quarter has passed. null when the figures are the latest that can be out, or the label can't be read. */
export function staleQuarter(label: string, lagDays: number, now: Date = new Date()): number | null {
  const end = periodEnd(label);
  if (!end) return null;
  const next = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() + 4, 0));     // the next quarter's last day
  if (now.getTime() < next.getTime() + lagDays * 86400000) return null;
  return (now.getUTCFullYear() - end.getUTCFullYear()) * 12 + now.getUTCMonth() - end.getUTCMonth();
}

/** "15 months old", "over 2 years old": for a marker beside dated figures. */
export function monthsOld(n: number): string {
  if (n >= 24) return `over ${Math.floor(n / 12)} years old`;
  return `${n} month${n === 1 ? "" : "s"} old`;
}

/** A headline's age beside its date once it is over a week old ("24 Sep 2026 · 2 weeks old"), so an old item never
 * reads as today's news; null for a fresh one (its "3 h ago" says enough). */
export function newsAge(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86400000);
  if (!Number.isFinite(days) || days < 7) return null;
  if (days < 60) { const w = Math.floor(days / 7); return `${w} week${w === 1 ? "" : "s"} old`; }
  return monthsOld(Math.floor(days / 30.4));
}
