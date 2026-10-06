/* The live breadth card (while the market is open): its types and the series drawn from its points. Pure, so the unit tests can read it. */

/** The live card while the market is open: points through the day (time, rose, fell, unchanged, then the counts above the 20-,
 * 50- and 200-day averages with how many stocks had each average, and the index level). */
export type LiveView = {
  state: "live" | "unavailable"; day: string; fields: string[]; points: (string | number | null)[][]; as_of: string | null;
  message: string | null; every_minutes: number;
  latest: { adv: number; dec: number; unch: number; a20: number; n20: number; a50: number; n50: number; a200: number; n200: number; idx: number | null;
    pct20: number | null; pct50: number | null; pct200: number | null } | null;
};
export type LiveSeries = { times: string[]; adv: number[]; dec: number[]; pct20: (number | null)[]; pct50: (number | null)[]; pct200: (number | null)[]; idx: (number | null)[] };
/** "Today, live as of 10:30": the live card's title. */
export const liveTitle = (live: Pick<LiveView, "as_of">) => (live.as_of ? `Today, live as of ${live.as_of}` : "Today, live");

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

