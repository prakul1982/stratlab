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
export function laterDays(days: { date: string; count: number; session?: boolean }[], today: string | null, region?: string): string[] {
  const after = today ? nextDay(today) : "";
  // LIVE10A-020: a US day that is no session (a Sunday, Thanksgiving) gets no chip: its dates are the source's estimates
  return [...new Set(days.filter((d) => d.count > 0 && d.date > after && !(region === "US" && d.session === false)).map((d) => d.date))].sort();
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

/** Whether the "Usual move" column has nothing to show (LIVE11A-019: "–" on every US row while it stayed): no row carries earlier moves
 * and every answer back has none (a "since the latest results" line alone included), once all rows or at least `enough` of them have been answered (rows past the reads' time limit are
 * never answered, and kept the column up before). */
export function movesEmpty(rows: { symbol: string; moves?: unknown }[], moves: Record<string, { moves?: unknown; since?: unknown } | null | undefined>, enough = 24): boolean {
  if (!rows.length || rows.some((r) => r.moves)) return false;
  const back = rows.filter((r) => moves[r.symbol] !== undefined);
  if (back.length < Math.min(rows.length, enough)) return false;
  // LIVE12A-008: a "since the latest results" line alone is no usual move: the column of "–" stayed for it (NVDA "– / since Tue 17 Nov")
  return back.every((r) => !moves[r.symbol]?.moves);
}
