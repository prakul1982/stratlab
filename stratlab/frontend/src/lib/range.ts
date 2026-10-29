/* The one range control every history chart uses (O4, 29 Oct): 1W 1M 3M 6M YTD 1Y 3Y 5Y All, plus "+ Custom" ("45 days",
 * "18 months"). A chip is offered only when the data reaches back further than it does (and shows a different stretch from the
 * chip before it), so "5Y" never sits on a chart with a year of data, and no two chips give the same view. The choice is
 * remembered per chart on this device. No imports: the unit tests load this file alone. */

export type RangeOption = { value: string; label: string };

const DAY = 86_400_000;
/** The presets, shortest first. A calendar month is a real month back (28 Feb to 28 Jan), not 30 days. */
const PRESETS: { value: string; label: string; back: (last: Date) => Date }[] = [
  { value: "1w", label: "1W", back: (d) => new Date(d.getTime() - 7 * DAY) },
  { value: "1m", label: "1M", back: (d) => monthsBack(d, 1) },
  { value: "3m", label: "3M", back: (d) => monthsBack(d, 3) },
  { value: "6m", label: "6M", back: (d) => monthsBack(d, 6) },
  { value: "ytd", label: "YTD", back: (d) => new Date(Date.UTC(d.getUTCFullYear(), 0, 1)) },
  { value: "1y", label: "1Y", back: (d) => monthsBack(d, 12) },
  { value: "3y", label: "3Y", back: (d) => monthsBack(d, 36) },
  { value: "5y", label: "5Y", back: (d) => monthsBack(d, 60) },
];
export const CUSTOM_UNITS = [
  { value: "days", label: "day", plural: "days" }, { value: "weeks", label: "week", plural: "weeks" },
  { value: "months", label: "month", plural: "months" }, { value: "years", label: "year", plural: "years" },
];
const CUSTOM = /^(\d{1,4}) (days|weeks|months|years)$/;

function monthsBack(d: Date, n: number): Date {
  const y = d.getUTCFullYear(), m = d.getUTCMonth() - n, day = d.getUTCDate();
  const t = new Date(Date.UTC(y, m, 1));
  const last = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + 1, 0)).getUTCDate();
  return new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), Math.min(day, last)));
}

/** Is this text a range this file knows: "all", a preset or "45 days". */
export const isRange = (r: unknown): r is string => typeof r === "string" && (r === "all" || PRESETS.some((p) => p.value === r) || CUSTOM.test(r));

/** The time a range starts at, counted back from `lastMs`; null for "all" (and anything unknown). */
export function rangeStart(id: string, lastMs: number): number | null {
  const last = new Date(lastMs);
  const p = PRESETS.find((x) => x.value === id);
  if (p) return p.back(last).getTime();
  const m = CUSTOM.exec(id);
  if (!m) return null;
  const n = Number(m[1]);
  return m[2] === "days" ? lastMs - n * DAY : m[2] === "weeks" ? lastMs - n * 7 * DAY : monthsBack(last, m[2] === "months" ? n : n * 12).getTime();
}

/** A time given as an ISO date or date-time, or milliseconds. */
export const toMs = (t: string | number): number => (typeof t === "number" ? t : Date.parse(t.length <= 10 ? `${t}T00:00:00Z` : t));

/** The index of the first point inside the range (times ascending); 0 for "all". */
export function rangeFrom(times: (string | number)[], id: string): number {
  if (times.length < 2 || id === "all") return 0;
  const start = rangeStart(id, toMs(times[times.length - 1]));
  if (start == null) return 0;
  let lo = 0, hi = times.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (toMs(times[mid]) < start) lo = mid + 1; else hi = mid; }
  return lo >= times.length ? 0 : lo;
}

/** The chips the data reaches, then "All": a preset only when it starts after the first point and shows a different stretch from the
 * one before it, and keeps at least two points. Fewer than two chips (a stretch too short to cut) offers none at all. */
export function offeredRanges(times: (string | number)[]): RangeOption[] {
  const out: RangeOption[] = [];
  if (times.length < 3) return out;
  const seen = new Set<number>();
  for (const p of PRESETS) {
    const i = rangeFrom(times, p.value);
    if (i > 0 && times.length - i >= 2 && !seen.has(i)) { seen.add(i); out.push({ value: p.value, label: p.label }); }
  }
  return out.length ? [...out, { value: "all", label: "All" }] : [];
}

/** "18 months" etc. as the chip's words; presets as their label. */
export function rangeLabel(id: string): string {
  const p = PRESETS.find((x) => x.value === id);
  if (p) return p.label;
  const m = CUSTOM.exec(id);
  if (m) { const n = Number(m[1]); const u = CUSTOM_UNITS.find((x) => x.value === m[2])!; return `${n} ${n === 1 ? u.label : u.plural}`; }
  return "All";
}

/** What the data covers, in words, for a "Showing …" line. */
export function spanWords(days: number): string {
  if (days >= 700) return `${(days / 365.25).toFixed(1).replace(/\.0$/, "")} years`;
  if (days >= 60) return `${Math.round(days / 30.44)} months`;
  return `${Math.round(days)} days`;
}

const KEY = "stratlab.range.";
/** The range last chosen on this chart on this device, or null. */
export function savedRange(chart: string): string | null {
  try { const v = localStorage.getItem(KEY + chart); return v && isRange(v) ? v : null; } catch { return null; }
}
export function saveRange(chart: string, id: string) {
  try { localStorage.setItem(KEY + chart, id); } catch { /* storage off: the choice still works for this visit */ }
}
/** The range to open on: the saved one when this chart still offers it (a custom one only when it cuts something), else "All". */
export function startRange(chart: string, times: (string | number)[], options: RangeOption[], initial = "all"): string {
  const saved = savedRange(chart);
  if (!saved) return options.some((o) => o.value === initial) ? initial : "all";
  if (saved === "all") return "all";
  if (options.some((o) => o.value === saved)) return saved;
  return CUSTOM.test(saved) && rangeFrom(times, saved) > 0 ? saved : "all";
}

/** The points (each with a `day`, ISO date or date-time) inside a range, counted back from that series' own last day. */
export function cutPoints<T extends { day: string }>(points: T[], id: string): T[] {
  return points.slice(rangeFrom(points.map((p) => p.day.slice(0, 10)), id));
}
