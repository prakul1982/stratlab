/* Numbers and dates for charts: axis ticks that land on round values, short money (₹ lakh / crore, $k / M), and time
 * axes that pick their own step (minutes, hours, days, months, years) with labels like "10:15", "1 Oct", "Oct '26".
 * Shared by every chart in the app, so the same number reads the same way everywhere. */

import { currencySymbol, fmtDate, fmtDateTime, SHORT_INR, SHORT_INTL, shortStep } from "./format";

const MINUS = "−";
const sign = (v: number) => (v < 0 ? MINUS : "");
/** 1.50 → "1.5", 2.00 → "2": no trailing zeros on short numbers. */
const trim = (s: string) => (s.includes(".") ? s.replace(/\.?0+$/, "") : s);

/** Round tick values covering lo..hi, about `count` of them (1, 2, 2.5 or 5 times a power of ten apart). */
export function niceTicks(lo: number, hi: number, count = 5): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  if (lo === hi) { lo -= 1; hi += 1; }
  if (lo > hi) [lo, hi] = [hi, lo];
  const raw = (hi - lo) / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : +v.toPrecision(12));
  return out;
}

/** The ticks with their labels, each label once: a tick that reads the same as one already kept ("1, 1, 1, 0" on a count
 * that rounds, "5%, 5%, 0%") is dropped, the first (lowest) one stays. */
export function distinctTicks(ticks: number[], format: (v: number) => string): [number[], string[]] {
  const seen = new Set<string>(), keep: number[] = [], labels: string[] = [];
  for (const t of ticks) {
    const l = format(t);
    if (seen.has(l)) continue;
    seen.add(l); keep.push(t); labels.push(l);
  }
  return [keep, labels];
}

/** Domain padded out to round ticks: [min, max] with a little air, plus the ticks inside it. */
export function niceDomain(lo: number, hi: number, count = 5, includeZero = false): { min: number; max: number; ticks: number[] } {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = 0; hi = 1; }
  if (includeZero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  if (lo === hi && lo === 0) hi = 1;                   // all zeros: draw them on the floor, not mid-air between −1 and 1
  else if (lo === hi) { const d = Math.abs(lo) * 0.05 || 1; lo -= d; hi += d; }
  const pad = (hi - lo) * 0.06;
  const min = includeZero && lo === 0 ? 0 : lo - pad, max = includeZero && hi === 0 ? 0 : hi + pad;
  return { min, max, ticks: niceTicks(min, max, count).filter((t) => t >= min && t <= max) };
}

/** A plain number, short: 950, 12.5k, 3.4L, 1.2Cr (Indian) or 950, 12.5k, 3.4M, 1.2B. */
export function compact(v: number, indian = true, dp = 1): string {
  const a = Math.abs(v);
  const f = (x: number, d = dp) => trim(x.toFixed(d));
  const step = shortStep(a, (indian ? SHORT_INR : SHORT_INTL).map(([d, u]) => [d, u, dp] as [number, string, number]));
  if (step) return `${sign(v)}${f(a / step[0], indian && step[1] === "Cr" && a >= 1e9 ? 0 : dp)}${step[1]}`;
  return `${sign(v)}${f(a, a >= 100 ? 0 : a >= 1 ? 2 : 4)}`;
}

/** Money for an axis or a tight spot: ₹12.5L, ₹1.2Cr, $12.4k. */
export function moneyCompact(v: number, currency = "INR", dp = 1): string {
  const c = compact(v, currency === "INR", dp);
  return c.startsWith(MINUS) ? MINUS + currencySymbol(currency) + c.slice(1) : currencySymbol(currency) + c;
}

/** A percentage tick: 12%, −3.5%, +4% when signed. */
export function pctTick(v: number, signed = false, dp = 1): string {
  return `${signed && v > 0 ? "+" : sign(v)}${trim(Math.abs(v).toFixed(dp))}%`;
}

/** A ratio or index level: 1.25, 0.8, 105. */
export function plainTick(v: number): string {
  const a = Math.abs(v);
  return sign(v) + trim(a.toFixed(a >= 100 ? 0 : a >= 10 ? 1 : 2));
}

/* ---------- time ---------- */

/** A time value as milliseconds: an ISO string, a "2026-10-01" day (read as local midday, so time zones never move it a
 * day), a Date or a number already in ms. */
export function toMs(t: string | number | Date): number {
  if (typeof t === "number") return t;
  if (t instanceof Date) return t.getTime();
  return /^\d{4}-\d{2}-\d{2}$/.test(t) ? new Date(`${t}T12:00:00`).getTime() : new Date(t).getTime();
}

const MIN = 60_000, HOUR = 60 * MIN, DAY = 24 * HOUR;
type Unit = "minute" | "hour" | "day" | "month" | "year";
const STEPS: [Unit, number, number][] = [        // [unit, how many, rough length in ms]
  ["minute", 1, MIN], ["minute", 5, 5 * MIN], ["minute", 15, 15 * MIN], ["minute", 30, 30 * MIN],
  ["hour", 1, HOUR], ["hour", 2, 2 * HOUR], ["hour", 3, 3 * HOUR], ["hour", 6, 6 * HOUR], ["hour", 12, 12 * HOUR],
  ["day", 1, DAY], ["day", 2, 2 * DAY], ["day", 7, 7 * DAY], ["day", 14, 14 * DAY],
  ["month", 1, 30 * DAY], ["month", 2, 61 * DAY], ["month", 3, 91 * DAY], ["month", 6, 182 * DAY],
  ["year", 1, 365 * DAY], ["year", 2, 730 * DAY], ["year", 5, 1826 * DAY], ["year", 10, 3652 * DAY],
];

const FMT = new Map<string, Intl.DateTimeFormat>();
/** The calendar parts of a moment in a time zone (formatters are cached: building one is the slow part). */
function parts(ms: number, tz?: string) {
  const k = tz ?? "";
  let f = FMT.get(k);
  if (!f) FMT.set(k, f = new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", hourCycle: "h23" }));
  const o = { y: 0, mo: 0, d: 0, h: 0, mi: 0 };
  for (const x of f.formatToParts(new Date(ms))) {
    if (x.type === "year") o.y = +x.value; else if (x.type === "month") o.mo = +x.value; else if (x.type === "day") o.d = +x.value;
    else if (x.type === "hour") o.h = +x.value; else if (x.type === "minute") o.mi = +x.value;
  }
  return o;
}

export type TimeTick = { t: number; label: string };

/** Whether a moment (already split into parts) is a tick of this step. */
function onStep(p: ReturnType<typeof parts>, unit: Unit, n: number): boolean {
  if (unit === "minute") return p.mi % n === 0;
  if (unit === "hour") return p.mi === 0 && p.h % n === 0;
  if (unit === "day") return n === 1 || (n === 2 ? p.d % 2 === 1 : n === 7 ? [1, 8, 15, 22].includes(p.d) : [1, 15].includes(p.d));
  if (unit === "month") return p.d === 1 && (p.mo - 1) % n === 0;
  return p.mo === 1 && p.d === 1 && p.y % n === 0;
}

/** Round-valued ticks for a time axis between t0 and t1 (ms), at most `max` of them. Intraday spans tick on clock
 * times ("10:15"), days on "1 Oct", months on "Oct", years (and each January on a month axis) on "2026". */
export function timeTicks(t0: number, t1: number, max = 6, tz?: string): TimeTick[] {
  if (!Number.isFinite(t0) || !Number.isFinite(t1)) return [];
  if (!(t1 > t0)) return [{ t: t0, label: tickLabel(t0, "day", tz) }];
  const [unit, n] = STEPS.find(([, , ms]) => (t1 - t0) / ms <= max) ?? STEPS[STEPS.length - 1];
  // walk in steps no coarser than the clock's quarter hours (India sits at +5:30), so a round time is never stepped over
  const step = unit === "minute" ? MIN * (n >= 5 ? 5 : 1) : unit === "hour" || (unit === "day" && n === 1) ? 15 * MIN : DAY;
  const out: TimeTick[] = [];
  let last = "";
  for (let t = Math.ceil(t0 / step) * step; t <= t1 && out.length < 60; t += step) {
    const p = parts(t, tz);
    if (unit === "day" && n === 1 && (p.h !== 0 || p.mi !== 0)) continue;
    const key = unit === "minute" || unit === "hour" ? `${p.d}-${p.h}-${p.mi}` : unit === "day" ? `${p.y}-${p.mo}-${p.d}` : unit === "month" ? `${p.y}-${p.mo}` : `${p.y}`;
    if (key === last || !onStep(p, unit, n)) continue;
    last = key;
    out.push({ t, label: tickLabel(t, unit, tz) });
  }
  return out.length ? out : [{ t: t0, label: tickLabel(t0, unit === "minute" || unit === "hour" ? unit : "day", tz) }];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** A tick's label; the turn of a year is written as the year itself ("2026"), the way it reads on a market chart. */
function tickLabel(ms: number, unit: Unit, tz?: string): string {
  const p = parts(ms, tz);
  const hhmm = `${String(p.h).padStart(2, "0")}:${String(p.mi).padStart(2, "0")}`;
  if (unit === "minute" || unit === "hour") return p.h === 0 && p.mi === 0 ? `${p.d} ${MONTHS[p.mo - 1]}` : hhmm;
  if (unit === "day") return p.mo === 1 && p.d === 1 ? String(p.y) : `${p.d} ${MONTHS[p.mo - 1]}`;
  if (unit === "month") return p.mo === 1 ? String(p.y) : MONTHS[p.mo - 1];
  return String(p.y);
}

/** A moment in full for a tooltip: "Fri 3 Oct 2026", or "3 Oct, 14:30" when intraday ("3 Oct, 14:30 IST" in a market's zone). */
export function tipTime(ms: number, intraday = false, tz?: string): string {
  const d = new Date(ms);
  return intraday
    ? fmtDateTime(d, { tz, year: false, zone: !!tz })
    : fmtDate(d, { tz, weekday: true });
}

/** True when the points sit closer than a day apart, so labels need clock times. */
export function isIntraday(ts: number[]): boolean {
  if (ts.length < 2) return false;
  let gap = Infinity;
  for (let i = 1; i < ts.length && i < 50; i++) gap = Math.min(gap, ts[i] - ts[i - 1]);
  return gap < 20 * HOUR;
}

/** Range presets: the ones that fit inside the data's span, then "All". */
export const RANGE_PRESETS: { id: string; label: string; days: number | null }[] = [
  { id: "1m", label: "1M", days: 31 }, { id: "3m", label: "3M", days: 92 }, { id: "6m", label: "6M", days: 183 },
  { id: "1y", label: "1Y", days: 366 }, { id: "all", label: "All", days: null },
];

/** True when every value is zero (or missing): a chart that is a flat line along the floor says "none in this period". */
export const flatZero = (...series: (number | null | undefined)[][]) => series.every((s) => s.every((v) => !v));
