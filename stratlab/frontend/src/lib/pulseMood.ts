import type { MoodMover, MoodQuoteRow, PulseMood } from "./research";

/* The Market pulse's figures as the page writes them (MOOD-1). One wording for every percentage (pct(v, 2) from format.ts:
 * two decimals, a sign, the true minus), so the table cell and the line above it never differ by a rounding. Pure, so the
 * unit tests can read them. */

/** A count with its digits grouped the Indian way (the breadth page's), a true minus for a change. */
export const whole = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? "–" : v.toLocaleString("en-IN", { maximumFractionDigits: 0 }).replace("-", "−"));

/** A signed count: "+105", "−3". */
export const signedWhole = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? "" : v === 0 ? "0" : `${v > 0 ? "+" : "−"}${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`);

/** A change in a share of stocks, in percentage points: "+1.4 pts". */
export const signedPts = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? "" : Number(v.toFixed(1)) === 0 ? "0.0 pts" : `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(1)} pts`);

/** Rupees crore with Indian grouping and a sign, as the flows table writes a net figure: "−₹2,800 cr". */
export function crore(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const body = `₹${Math.abs(Math.round(v)).toLocaleString("en-IN")} cr`;
  return v === 0 ? body : `${v > 0 ? "+" : "−"}${body}`;
}

/** The level of one of the "volatility, currencies and rates" rows, in the unit a reader knows it by. */
export function riskLevel(r: Pick<MoodQuoteRow, "label" | "tag" | "price">): string {
  const n = (dp: number) => r.price.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  if (r.tag === "yield") return `${n(2)}%`;
  if (r.tag === "oil") return `$${n(2)}`;
  if (r.tag === "gold") return `$${n(0)}`;
  if (r.label === "USD/INR") return `₹${n(2)}`;
  return n(2);
}

/** Two tables side by side only when they have the same number of rows, else one above the other: a pair of different heights
 * leaves a hole under the shorter (the owner's "dead space" rule). */
export const pairable = (a: number, b: number): boolean => a > 0 && b > 0 && a === b;

/** The movers table's rows: the most points added first, then the most taken, as one list ordered by points. */
export function moverRows(m: NonNullable<PulseMood["movers"]>[number]): MoodMover[] {
  return [...m.adding, ...m.taking].sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
}

/** "ICICI Bank +1.05%, HDFC Bank −1.19%": what moved a sector, from its largest members. */
export function movedBy(movers: { symbol: string; name?: string; change_pct: number }[], pctFn: (v: number) => string): string {
  return movers.map((m) => `${m.name ?? m.symbol} ${pctFn(m.change_pct)}`).join(", ");
}

/** The rows of the story marker: which headlines the main story counts (positions in the story's own list). */
export function storyOf(story: { label: string; indices: number[]; headlines: string[] } | null | undefined, headline: string): string | null {
  if (!story) return null;
  const i = story.headlines.indexOf(headline);
  return i >= 0 && story.indices.includes(i) ? story.label : null;
}

/** The sentence that says how many of the sector table's rows rose and fell (the table's own count, no other). */
export const sectorCount = (s: NonNullable<PulseMood["sectors"]>): string =>
  `${s.up} of ${s.of} sector indices rose, ${s.down} fell${s.unchanged ? `, ${s.unchanged} unchanged` : ""}`;

/** Points an index gained or lost to one company: "+55.3", "−32.0". */
export const signedPoints = (v: number | null | undefined): string => (v == null || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`);

/** "Companies in today's headlines" holds companies: a row the read named after a group ("Indian IT stocks", "PSU banks", "metal
 * shares") is not one, and pinning it on one symbol says more than the headline did (LIVE4-006: "Indian IT stocks → INFY"). */
export const groupPhrase = (name: string): boolean =>
  /\b(stocks|shares|sectors?|companies|firms|names|counters|banks|lenders|majors|makers|pack|index|indices|space)\s*$/i.test(name.trim());
export function companyRows<T extends { name: string }>(hot: T[]): T[] {
  return hot.filter((h) => !groupPhrase(h.name));
}

/** The column over the day's figures: "Today" while the market's session is today's, else that session's day (LIVE4-007: a
 * "Today" column on a page titled "How the market felt at the last close"). */
export const sessionHeader = (closedDay: string | null | undefined, dayText: (iso: string) => string): string => (closedDay ? dayText(closedDay) : "Today");

/** The session Mood's tables are of, for their headers: the read's own session when it is behind the index levels (LIVE7A-001: between
 * the close and Mood's next read, the tables below the levels were the last session's figures under the new day's date), else the
 * levels' closed day (null while they trade). */
export function moodDay(m: Pick<PulseMood, "session" | "behind"> | null | undefined, closedDay: string | null): string | null {
  if (m?.session && (m.behind || (closedDay && m.session < closedDay))) return m.session;
  return closedDay;
}

/** The line that says a read is of an earlier session than the index levels above it, or null. */
export function moodBehindNote(m: Pick<PulseMood, "session" | "behind"> | null | undefined, closedDay: string | null, dayText: (iso: string) => string): string | null {
  const own = moodDay(m, closedDay);
  if (!m?.session || own !== m.session || own === closedDay) return null;
  const newer = m.behind ?? closedDay;
  return `These figures are of the ${dayText(m.session)} session${newer ? `; the ${dayText(newer)} session's are being read` : ""}.`;
}

/** A row's move: a yield's in basis points ("+12 bp"), every other one in percent (LIVE7A-023: "4.98% +2.45%" was a 12 bp rise). */
export const quoteMove = (r: Pick<MoodQuoteRow, "change_pct" | "change_bp">): { value: number | null; text: string } =>
  r.change_bp != null ? { value: r.change_bp, text: `${r.change_bp > 0 ? "+" : r.change_bp < 0 ? "−" : ""}${Math.abs(r.change_bp)} bp` }
    : { value: r.change_pct, text: r.change_pct == null ? "–" : `${r.change_pct > 0 ? "+" : r.change_pct < 0 ? "−" : ""}${Math.abs(r.change_pct).toFixed(2)}%` };

/** "today", or the session's day when a market's latest session isn't today's (worked out now, not when the read was made). */
export const sessionWord = (day: string | null | undefined, today: string, dayText: (iso: string) => string): string => (day && day !== today ? `on ${dayText(day)}` : "today");
