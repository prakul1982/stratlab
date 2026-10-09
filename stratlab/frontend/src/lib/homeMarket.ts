/* The reader's own market: India, StratLab's home market, unless the browser's clock is in the Americas (the US market).
 * Pages whose first view is about one market (Red flags, the Invest home's breadth card) open on it, whatever market a
 * company page was last looked up in (R7O-003: Red flags opened on the US with an empty watchlist for an India reader;
 * R6O-007: the breadth card followed an old S&P 500 pick). No imports, so the unit tests load it alone. */

export type HomeRegion = "IN" | "US";

/** The browser's time zone, or "" when it can't say. */
export function browserZone(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; } catch { return ""; }
}

/** "US" for a reader whose clock is in the Americas, else "IN". */
export function homeRegion(zone: string = browserZone()): HomeRegion {
  return /^America\//.test(zone) ? "US" : "IN";
}
