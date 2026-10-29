/* A period of days chosen on a chart: a preset ("3m", "1y"), "all", or one typed under "+ Custom" ("45 days", "18 months").
 * Pages that draw a daily history ask for all of it once and cut it with these, so every choice answers at once, and a
 * choice the stored days can't tell apart from "All" isn't offered. No imports: the unit tests load this file alone. */

// the owner's set (29 Oct): 1W 1M 3M 6M YTD 1Y 3Y 5Y All. "ytd" has no fixed length: it runs from 1 January of the last day's year
// (periodDays and firstInPeriod take the last day for it). "2y" stays for a pick saved before.
export const PRESET_DAYS: Record<string, number> = { "1w": 7, "1m": 30, "3m": 91, "6m": 182, "1y": 365, "2y": 730, "3y": 1095, "5y": 1826 };
const UNIT_DAYS: Record<string, number> = { days: 1, weeks: 7, months: 30.44, years: 365.25 };
const DAY_MS = 86_400_000;

/** Is this text a period this file knows: "all", a preset, or "35 days". */
export const isPeriod = (p: unknown): p is string =>
  typeof p === "string" && (p === "all" || p === "ytd" || p in PRESET_DAYS || /^\d{1,4} (days|weeks|months|years)$/.test(p));

/** The calendar days from 1 January of a day's year to that day. */
const sinceNewYear = (last: string) => Math.round((Date.parse(last) - Date.parse(`${last.slice(0, 4)}-01-01`)) / DAY_MS);

/** How many calendar days a period covers, or null for all of them (`last`, the last day shown, for "ytd"). */
export function periodDays(p: string, last?: string): number | null {
  if (p === "ytd") return last ? sinceNewYear(last) : null;
  if (p in PRESET_DAYS) return PRESET_DAYS[p];
  const m = p.match(/^(\d{1,4}) (days|weeks|months|years)$/);
  return m ? Math.round(Number(m[1]) * UNIT_DAYS[m[2]]) : null;
}

/** The calendar days from the first to the last of the days (ISO dates, oldest first). */
export function spanDays(days: string[]): number {
  return days.length > 1 ? (Date.parse(days[days.length - 1]) - Date.parse(days[0])) / DAY_MS : 0;
}

/** The index of the first day inside the period, counted back from the last day. */
export function firstInPeriod(days: string[], p: string): number {
  const d = periodDays(p, days[days.length - 1]);
  if (d == null || days.length === 0) return 0;
  const cut = Date.parse(days[days.length - 1]) - d * DAY_MS;
  const i = days.findIndex((x) => Date.parse(x) >= cut);
  return i < 0 ? 0 : i;
}

/** Every series of a history (all the same length as its days) from the index on. */
export function cutSeries<T extends Record<string, unknown[]>>(h: T, from: number): T {
  if (from <= 0) return h;
  return Object.fromEntries(Object.entries(h).map(([k, v]) => [k, v.slice(from)])) as T;
}

/** The presets worth offering for this many stored calendar days: only those shorter than the whole history (a longer one
 * would show exactly what "All" shows), in order, then "All". */
export function offeredPresets(span: number, last?: string): { value: string; label: string }[] {
  const labels: Record<string, string> = { "1w": "1W", "1m": "1M", "3m": "3M", "6m": "6M", ytd: "YTD", "1y": "1Y", "2y": "2Y", "3y": "3Y", "5y": "5Y" };
  // shortest first; "2y" is no longer offered (3Y and 5Y are), but a pick of it saved before still works
  const days: [string, number | null][] = [["1w", 7], ["1m", 30], ["3m", 91], ["6m", 182], ["ytd", last ? sinceNewYear(last) : null], ["1y", 365], ["3y", 1095], ["5y", 1826]];
  const fit = days.filter(([, d]) => d != null && d >= 7 && span > d).sort((a, b) => a[1]! - b[1]!).map(([value]) => ({ value, label: labels[value] }));
  return [...fit, { value: "all", label: "All" }];
}
