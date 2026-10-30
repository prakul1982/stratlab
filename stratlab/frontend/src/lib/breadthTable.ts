import { MOVES_LABEL } from "./breadthLive";           // not "./breadth": that one reaches the API client, and the unit tests load this file alone
import type { History, Today } from "./breadth";

/* The breadth figures of a day as ONE table (MOOD-1, owner: "table it"): a measure, its day, the day before, the change and the
 * average of the last 20 days where the stored history has it. Pure, so the unit tests read it. */

export type Unit = "count" | "pct" | "num" | "ratio" | "level";
export type Part = { now: number | null; before: number | null; change: number | null; avg: number | null; unit: Unit; tone?: "up" | "down" };
export type MeasureRow = { key: string; label: string; means: string; info: "ad" | "ma" | "highs_lows" | "moves" | "stage2" | "mcclellan" | "summation" | "trin" | null; parts: Part[] };

/** The mean of the last 20 days of a series (today's included), skipping days with no value; null with under 5 of them. */
export function avg20(series: (number | null)[] | undefined): number | null {
  const v = (series ?? []).slice(-20).filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  return v.length >= 5 ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

const fig = (t: Today, k: keyof Today & string, h: History | null, series: keyof History | null, unit: Unit, extra: Partial<Part> = {}): Part => {
  const f = t[k as "adv"];
  return { now: f.value, before: f.prev, change: f.change, avg: series && h ? avg20(h[series] as (number | null)[]) : null, unit, ...extra };
};

/** The rows, in the order the page has always listed the figures. A pair (rose / fell) is one row with two parts. */
export function measureRows(t: Today, h: History | null): MeasureRow[] {
  return [
    { key: "ad", label: "Rose / fell", means: "Stocks that closed above / below the previous close.", info: "ad", parts: [fig(t, "adv", h, "adv", "count", { tone: "up" }), fig(t, "dec", h, "dec", "count", { tone: "down" })] },
    { key: "ratio", label: "Rose for each fell", means: "Risers divided by fallers.", info: "ad", parts: [fig(t, "ad_ratio", h, "ad_ratio", "ratio")] },
    { key: "p20", label: "Above 20-day average", means: "Share of stocks priced above their 20-day average.", info: "ma", parts: [fig(t, "pct20", h, "pct20", "pct")] },
    { key: "p50", label: "Above 50-day average", means: "Share of stocks priced above their 50-day average.", info: "ma", parts: [fig(t, "pct50", h, "pct50", "pct")] },
    { key: "p200", label: "Above 200-day average", means: "Share of stocks priced above their 200-day average.", info: "ma", parts: [fig(t, "pct200", h, "pct200", "pct")] },
    { key: "hl", label: "52-week highs / lows", means: "Stocks at their highest / lowest price of the past year.", info: "highs_lows", parts: [fig(t, "highs", h, "highs", "count", { tone: "up" }), fig(t, "lows", h, "lows", "count", { tone: "down" })] },
    { key: "mv", label: MOVES_LABEL, means: "Stocks that moved 4% or more in a day, up / down.", info: "moves", parts: [fig(t, "up4", h, "up4", "count", { tone: "up" }), fig(t, "down4", h, "down4", "count", { tone: "down" })] },
    { key: "s2", label: "In Stage 2", means: "Share of stocks in a Stage 2 uptrend.", info: "stage2", parts: [fig(t, "stage2", h, "stage2", "pct")] },
    { key: "mc", label: "McClellan oscillator", means: "A fast against a slow average of net risers.", info: "mcclellan", parts: [fig(t, "mcclellan", h, "mcclellan", "num")] },
    { key: "su", label: "McClellan summation", means: "The oscillator added up from the first stored day.", info: "summation", parts: [fig(t, "summation", h, "summation", "num")] },
    { key: "tr", label: "TRIN", means: "Risers per faller against their volumes.", info: "trin", parts: [fig(t, "trin", h, "trin", "ratio")] },
  ];
}

const nf = (v: number, dp: number) => v.toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp }).replace("-", "−");

/** A figure as its unit writes it: a count grouped the Indian way, a share with one decimal, an oscillator with one, a ratio with two. */
export function figure(v: number | null | undefined, unit: Unit): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return unit === "count" ? nf(Math.round(v), 0) : unit === "pct" ? `${v.toFixed(1)}%` : unit === "ratio" ? v.toFixed(2) : unit === "level" ? nf(v, 2) : nf(v, 1);
}

/** A change as its unit writes it, signed: "+105", "−0.6 pts", "+8.6", "+0.13". A change that rounds to nothing is "no change". */
export function change(v: number | null | undefined, unit: Unit): string {
  if (v == null || !Number.isFinite(v)) return "";
  const dp = unit === "count" ? 0 : unit === "ratio" || unit === "level" ? 2 : 1;
  const r = Number(v.toFixed(dp));
  if (r === 0) return "no change";
  return `${r > 0 ? "+" : "−"}${Math.abs(r).toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp })}${unit === "pct" ? " pts" : ""}`;
}

/** The live card's rows: the count so far today, the last close's, and the difference. `l` is the newest live point, `t` the last close's
 * figures, `lastLevel` the index's last close; the index row's close is "–" when the history isn't loaded. */
export function liveRows(l: { adv: number; dec: number; pct20: number | null; pct50: number | null; pct200: number | null; idx: number | null }, t: Today, indexName: string, lastLevel: number | null): MeasureRow[] {
  const part = (now: number | null, before: number | null, unit: Unit, extra: Partial<Part> = {}): Part => ({ now, before, change: now != null && before != null ? now - before : null, avg: null, unit, ...extra });
  return [
    { key: "ad", label: "Rose / fell", means: "Stocks above / below the previous close so far today.", info: "ad", parts: [part(l.adv, t.adv.value, "count", { tone: "up" }), part(l.dec, t.dec.value, "count", { tone: "down" })] },
    { key: "p20", label: "Above 20-day average", means: "Share of stocks priced above their 20-day average.", info: "ma", parts: [part(l.pct20, t.pct20.value, "pct")] },
    { key: "p50", label: "Above 50-day average", means: "Share of stocks priced above their 50-day average.", info: "ma", parts: [part(l.pct50, t.pct50.value, "pct")] },
    { key: "p200", label: "Above 200-day average", means: "Share of stocks priced above their 200-day average.", info: "ma", parts: [part(l.pct200, t.pct200.value, "pct")] },
    ...(l.idx != null ? [{ key: "idx", label: indexName, means: "The group's index, latest level.", info: null, parts: [part(l.idx, lastLevel, "level")] } as MeasureRow] : []),
  ];
}
