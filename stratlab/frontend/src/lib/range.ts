/* The one range control every history chart uses (O4, 29 Oct): 1W 1M 3M 6M YTD 1Y 3Y 5Y All, plus "+ Custom" ("45 days", "18 months").
 * The set, its lengths and the rule that a chip is offered only when the data reaches further back than it does are lib/period.ts's (the
 * one source, which Market breadth reads too); this file adds what a chart needs on top of it: the cut of a series, "never two chips
 * for the same view", and the choice remembered per chart on this device. */
import { firstInPeriod, isPeriod, offeredPresets, periodDays, spanDays } from "./period";

export type RangeOption = { value: string; label: string };
export { isPeriod as isRange };

const DAY = 86_400_000;
/** An ISO date, or a time in milliseconds, as an ISO day. */
const dayOf = (t: string | number): string => (typeof t === "number" ? new Date(t).toISOString().slice(0, 10) : t.slice(0, 10));
export const toMs = (t: string | number): number => (typeof t === "number" ? t : Date.parse(t.length <= 10 ? `${t}T00:00:00Z` : t));

/** The index of the first point inside the range (points ascending); 0 for "all". */
export function rangeFrom(times: (string | number)[], id: string): number {
  if (times.length < 2 || id === "all") return 0;
  const days = times.map(dayOf);
  const i = firstInPeriod(days, id);
  return i >= times.length ? 0 : i;
}

/** The time a range starts at counted back from `lastMs`, for a chart that works in milliseconds; null for "all". */
export function rangeStart(id: string, lastMs: number): number | null {
  const d = periodDays(id, new Date(lastMs).toISOString().slice(0, 10));
  return d == null ? null : lastMs - d * DAY;
}

/** The chips the data reaches, then "All": a preset only when it starts after the first point, keeps two points and shows a different
 * stretch from the one before it. A stretch too short to cut (under three points) offers none. */
export function offeredRanges(times: (string | number)[]): RangeOption[] {
  if (times.length < 3) return [];
  const days = times.map(dayOf);
  const seen = new Set<number>();
  const out: RangeOption[] = [];
  for (const o of offeredPresets(spanDays(days), days[days.length - 1])) {
    if (o.value === "all") continue;
    const i = firstInPeriod(days, o.value);
    if (i > 0 && days.length - i >= 2 && !seen.has(i)) { seen.add(i); out.push(o); }
  }
  return out.length ? [...out, { value: "all", label: "All" }] : [];
}

const UNITS: Record<string, [string, string]> = { days: ["day", "days"], weeks: ["week", "weeks"], months: ["month", "months"], years: ["year", "years"] };
/** The chip's words: a preset as its label, "18 months" as it was typed. */
export function rangeLabel(id: string): string {
  const preset = offeredPresets(1e9, "2026-12-31").find((o) => o.value === id);
  if (preset) return preset.label;
  const m = /^(\d{1,4}) (days|weeks|months|years)$/.exec(id);
  if (m) { const n = Number(m[1]); return `${n} ${UNITS[m[2]][n === 1 ? 0 : 1]}`; }
  return id === "2y" ? "2Y" : "All";
}

/** What the data covers, in words, for a "this chart has …" line. */
export function spanWords(days: number): string {
  if (days >= 700) return `${(days / 365.25).toFixed(1).replace(/\.0$/, "")} years`;
  if (days >= 60) return `${Math.round(days / 30.44)} months`;
  return `${Math.round(days)} days`;
}

/** The points (each with a `day`, ISO date or date-time) inside a range, counted back from that series' own last day. */
export function cutPoints<T extends { day: string }>(points: T[], id: string): T[] {
  return points.slice(rangeFrom(points.map((p) => p.day.slice(0, 10)), id));
}

const KEY = "stratlab.range.";
/** The range last chosen on this chart on this device, or null. */
export function savedRange(chart: string): string | null {
  try { const v = localStorage.getItem(KEY + chart); return v && isPeriod(v) ? v : null; } catch { return null; }
}
export function saveRange(chart: string, id: string) {
  try { localStorage.setItem(KEY + chart, id); } catch { /* storage off: the choice still works for this visit */ }
}
/** The range to open on: the saved one when this chart still offers it (a custom one only when it cuts something), else `initial`, else "All". */
export function startRange(chart: string, times: (string | number)[], options: RangeOption[], initial = "all"): string {
  const saved = savedRange(chart);
  if (!saved) return options.some((o) => o.value === initial) ? initial : "all";
  if (saved === "all") return "all";
  if (options.some((o) => o.value === saved)) return saved;
  return /^\d{1,4} (days|weeks|months|years)$/.test(saved) && rangeFrom(times, saved) > 0 ? saved : "all";
}

/** The custom choices remembered for a chart that the chart's data no longer reaches are dropped from storage, so the row never shows a
 * chip that gives the same view as "All" (the chip bar reads its remembered choices when it opens). */
export function pruneCustom(storageKey: string, times: (string | number)[]) {
  try {
    const raw = JSON.parse(localStorage.getItem(storageKey) ?? "[]");
    if (!Array.isArray(raw)) return;
    const kept = raw.filter((o: { value?: unknown }) => typeof o?.value === "string" && rangeFrom(times, o.value) > 0);
    if (kept.length !== raw.length) localStorage.setItem(storageKey, JSON.stringify(kept));
  } catch { /* storage off */ }
}
