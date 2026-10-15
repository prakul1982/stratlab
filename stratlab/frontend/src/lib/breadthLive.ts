/* The live breadth card (while the market is open): its types and the series drawn from its points. Pure, so the unit tests can read it. */

/** The live card while the market is open: points through the day (time, rose, fell, unchanged, then the counts above the 20-,
 * 50- and 200-day averages with how many stocks had each average, and the index level). */
export type LiveView = {
  state: "live" | "unavailable"; day: string; fields: string[]; points: (string | number | null)[][]; as_of: string | null;
  message: string | null; every_minutes: number;
  /** minutes since the newest point, and whether that is over 20 while the market trades (older servers send neither) */
  age_minutes?: number | null; late?: boolean;
  latest: { adv: number; dec: number; unch: number; a20: number; n20: number; a50: number; n50: number; a200: number; n200: number; idx: number | null;
    pct20: number | null; pct50: number | null; pct200: number | null;
    /** the group's size and its stocks with no price today (older points have neither) */
    of?: number | null; unread?: number | null } | null;
};
export type LiveSeries = { times: string[]; adv: number[]; dec: number[]; pct20: (number | null)[]; pct50: (number | null)[]; pct200: (number | null)[]; idx: (number | null)[] };

const minutes = (n: number) => `${n} minute${n === 1 ? "" : "s"}`;

/** "Today, live as of 10:30": the live card's title. When the newest point is over 20 minutes old while the market trades it
 * says so instead: "Last updated 09:15, 25 minutes ago" (R24-002: "Live as of 09:15" stood for 27 minutes). */
export const liveTitle = (live: Pick<LiveView, "as_of"> & Partial<Pick<LiveView, "late" | "age_minutes">>) =>
  live.late && live.as_of ? `Last updated ${live.as_of}${live.age_minutes != null ? `, ${minutes(live.age_minutes)} ago` : ""}`
    : live.as_of ? `Today, live as of ${live.as_of}` : "Today, live";

/** The card's tag: "Live" in the live colour, or "Delayed" once the newest point is late. */
export const liveTag = (live: Partial<Pick<LiveView, "late">>): { tone: "live" | "warn"; text: string } =>
  live.late ? { tone: "warn", text: "Delayed" } : { tone: "live", text: "Live" };

const n = (v: number) => v.toLocaleString("en-IN");

/** How many of the group's stocks the counts cover, so rose + fell + unchanged reconciles with the group (R24-003: 2,344 of
 * All NSE's 2,563 with nothing said about the rest): "2,344 of 2,563 stocks read · 219 without a price yet today (not traded
 * yet, suspended or not quoted)". Null for a point without the group's size. */
export function liveReadLine(l: Pick<NonNullable<LiveView["latest"]>, "adv" | "dec" | "unch" | "of">): string | null {
  if (l.of == null || !(l.of > 0)) return null;
  const read = l.adv + l.dec + l.unch, left = Math.max(0, l.of - read);
  return `${n(read)} of ${n(l.of)} stocks read` + (left ? ` · ${n(left)} without a price yet today (not traded yet, suspended or not quoted)` : "");
}

/** The page header's chip above a live card: the numbers under the chip are the last close's, so it says so (R24-011:
 * "Prices as of 14 Oct" above "Today, live as of 09:15"). */
export const breadthChipLabel = (live: unknown) => (live ? "Last close" : "Prices as of");

/** The live points as one series per measure (a share is the count above the average over the stocks that had that average). */
export function liveSeries(live: Pick<LiveView, "fields" | "points">): LiveSeries {
  const at = (name: string) => live.fields.indexOf(name) + 1;      // column 0 of a point is its time
  const col = (name: string) => live.points.map((p) => (p[at(name)] as number | null) ?? null);
  const share = (a: string, n: string) => live.points.map((p) => {
    const x = p[at(a)] as number | null, y = p[at(n)] as number | null;
    return x == null || !y ? null : Math.round((x / y) * 10000) / 100;
  });
  return { times: live.points.map((p) => String(p[0])), adv: col("adv") as number[], dec: col("dec") as number[],
    pct20: share("a20", "n20"), pct50: share("a50", "n50"), pct200: share("a200", "n200"), idx: col("idx") };
}

