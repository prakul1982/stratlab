/* A period of days chosen on a chart: a preset ("3m", "1y"), "all", or one typed under "+ Custom" ("45 days", "18 months").
 * Pages that draw a daily history ask for all of it once and cut it with these, so every choice answers at once, and a
 * choice the stored days can't tell apart from "All" isn't offered. No imports: the unit tests load this file alone. */

export const PRESET_DAYS: Record<string, number> = { "3m": 91, "6m": 182, "1y": 365, "2y": 730 };
const UNIT_DAYS: Record<string, number> = { days: 1, weeks: 7, months: 30.44, years: 365.25 };
const DAY_MS = 86_400_000;

/** Is this text a period this file knows: "all", a preset, or "35 days". */
export const isPeriod = (p: unknown): p is string =>
  typeof p === "string" && (p === "all" || p in PRESET_DAYS || /^\d{1,3} (days|weeks|months|years)$/.test(p));

/** How many calendar days a period covers, or null for all of them. */
export function periodDays(p: string): number | null {
  if (p in PRESET_DAYS) return PRESET_DAYS[p];
  const m = p.match(/^(\d{1,3}) (days|weeks|months|years)$/);
  return m ? Math.round(Number(m[1]) * UNIT_DAYS[m[2]]) : null;
}

/** The calendar days from the first to the last of the days (ISO dates, oldest first). */
export function spanDays(days: string[]): number {
  return days.length > 1 ? (Date.parse(days[days.length - 1]) - Date.parse(days[0])) / DAY_MS : 0;
}

/** The index of the first day inside the period, counted back from the last day. */
export function firstInPeriod(days: string[], p: string): number {
  const d = periodDays(p);
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
export function offeredPresets(span: number): { value: string; label: string }[] {
  const labels: Record<string, string> = { "3m": "3M", "6m": "6M", "1y": "1Y", "2y": "2Y" };
  const fit = Object.entries(PRESET_DAYS).filter(([, d]) => span > d).map(([value]) => ({ value, label: labels[value] }));
  return [...fit, { value: "all", label: "All" }];
}
