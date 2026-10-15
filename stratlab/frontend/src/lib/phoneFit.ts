/** Small helpers that keep labels and tables inside a phone-width screen (round 25). */

/** A year label in four characters of year or less: "FY2017" → "FY17", "Mar 2017" → "Mar 17", "2017" → "17". */
export function shortYear(y: string): string {
  return y.replace(/(^|\D)(?:19|20)(\d{2})(?!\d)/, "$1$2");
}

/** A bar's value for a chart of many narrow bars, in the units' own style: 1,46,882 cr → "1.47L", 28,046 → "28k",
 * 2,812 stays "2,812". Null when `trendValue` already says it as briefly. */
export function compactValue(v: number, unit: string): string | null {
  if (/billion|lakh/i.test(unit) || !/cr/i.test(unit)) return null;
  const a = Math.abs(v), sign = v < 0 ? "−" : "";
  if (a >= 100000) return `${sign}${(a / 100000).toFixed(2)}L`;
  if (a >= 10000) { const k = a / 1000; return `${sign}${k >= 100 ? Math.round(k) : Math.round(k * 10) / 10}k`; }
  return null;
}

/** Whether bar `i` of `n` carries its labels when the bars are too narrow for all of them: every other one, counting
 * back from the latest, so the newest is always named. */
export function labelledBar(i: number, n: number): boolean {
  return (n - 1 - i) % 2 === 0;
}

/** Bars are crowded from this many on (on a phone, CSS then drops the in-between labels). */
export const DENSE_BARS = 8;

/** Scrolls a box to its right end, so the newest column of a period table is the one in view. */
export function scrollToEnd(el: { scrollLeft: number; scrollWidth: number; clientWidth: number } | null): void {
  if (el && el.scrollWidth > el.clientWidth) el.scrollLeft = el.scrollWidth - el.clientWidth;
}

/** Where a chart note goes: starting at `x`, `width` wide, inside [left, right]. It starts at `x` when it fits, else it
 * ends at the right edge. */
export function clampNote(x: number, width: number, left: number, right: number): { x: number; anchor: "start" | "end" } {
  if (x + width <= right) return { x: Math.max(x, left), anchor: "start" };
  return { x: right, anchor: "end" };
}

/** How long a placeholder may show before it says the load is slow and offers Retry. */
export const SLOW_LOAD_MS = 8000;
export const SLOW_LOAD_NOTE = "Still loading… this can take a little longer the first time today";
