/* The results calendar's rows: pure helpers the page and the unit tests share (rel1, LIVE9A-014). */

/** The day after an ISO day, as an ISO day. */
export function nextDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** The day chips after "Today" and "Tomorrow": one per later day that has companies on it. A day gone by, today and tomorrow again by
 * their dates, and a day with nobody reporting (a weekend, an exchange holiday) are left out (LIVE9A-014: "Today, Tomorrow, Mon 16 Nov,
 * Wed 18 Nov" listed a past day and tomorrow twice; Thu 26 Nov, a US holiday, had a chip). */
export function laterDays(days: { date: string; count: number }[], today: string | null): string[] {
  const after = today ? nextDay(today) : "";
  return [...new Set(days.filter((d) => d.count > 0 && d.date > after).map((d) => d.date))].sort();
}

/** The market value at the price shown beside it: the stored value scaled by the live price against the stored close it was worked out
 * at (LIVE9A-014: NVDA "$3.92T · $155.58", the value of the last close beside a live price). Unchanged without both prices, or when the
 * two are too far apart for a day's move (a split, a bad read): then the stored value stands. */
export function capAt(cap: number | null | undefined, last: number | null | undefined, live: number | null | undefined): number | null {
  if (cap == null) return null;
  if (!last || !live || last <= 0 || live <= 0) return cap;
  const k = live / last;
  return k >= 0.5 && k <= 2 ? cap * k : cap;
}

/** When a company reports, short, for its own place on the row's first line: "After the close", "Before the open". */
export const whenShort = (when: string | null | undefined): string | null =>
  when ? when.replace(/^./, (c) => c.toUpperCase()) : null;
