import { api } from "./api";
import type { LiveView } from "./breadthLive";
import { fmtDate, latestDue, type Pending } from "./format";
export { breadthChipLabel, dailyTitle, liveReadLine, liveNoticeTone, liveSeries, liveTag, liveTitle, MOVES_LABEL, MOVES_TITLE, sectorColumnLabel } from "./breadthLive";
export { BROAD_GROUP, MARKET_GROUP, breadthStart, groupRegion, orderGroups, savePick, savedPick } from "./breadthPick";
export type { LiveSeries, LiveView } from "./breadthLive";

/* Market breadth: how many stocks in a group take part in the market's moves. Counts and shares from the server,
 * worked out after each close; facts, never a call on the market. */

export type GroupId = "nse_all" | "nifty50" | "nifty500" | "midcap150" | "smallcap250" | "us_large" | "sp500";
export type RangeId = "3m" | "6m" | "1y" | "2y" | "all";
export type Group = { id: GroupId; name: string; region: "IN" | "US"; index_name: string };
export type Figure = { value: number | null; prev: number | null; change: number | null };
export type Headline = "adv" | "dec" | "unch" | "ad_ratio" | "pct20" | "pct50" | "pct200" | "highs" | "lows" | "up4" | "down4"
  | "stage2" | "mcclellan" | "summation" | "thrust" | "trin" | "stocks";
export type Today = { day: string; prev_day: string | null } & Record<Headline, Figure>;
export type History = {
  days: string[]; adv: number[]; dec: number[]; unch: number[]; stocks: number[]; net: number[]; ad_line: number[];
  ad_ratio: (number | null)[]; pct20: (number | null)[]; pct50: (number | null)[]; pct200: (number | null)[];
  highs: number[]; lows: number[]; net_highs: number[]; up4: number[]; down4: number[]; stage2: (number | null)[];
  mcclellan: number[]; summation: number[]; thrust: number[]; trin: (number | null)[]; index: (number | null)[];
};
export type SectorTable = { columns: { label: string; day: string }[]; rows: { sector: string; stocks: number; values: (number | null)[] }[];
  /** sectors with too few stocks to show a share, named so the table adds up (DE-024) */
  small?: { sector: string; stocks: number }[]; min_stocks?: number };

/** A cap for a chart whose rare spike would flatten every other day (DE-022: one TRIN near 10 among values around 1):
 * 1.5 times the 95th percentile, never under `floor`; null when nothing goes above it. */
export function spikeCap(values: (number | null)[], floor = 3): number | null {
  const v = values.filter((x): x is number => x != null && Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length < 10) return null;
  const cap = Math.max(floor, v[Math.floor(0.95 * (v.length - 1))] * 1.5);
  return v[v.length - 1] > cap ? Math.round(cap * 10) / 10 : null;
}
export type BreadthView = {
  group: Group; groups: Group[]; today: Today | null; as_of: string | null; since: string | null; range: RangeId;
  help: Record<string, string>; status: string | null; locked: boolean; plan_needed: string;
  history: History | null; sectors: SectorTable | null; thrusts: string[] | null; live: LiveView | null;
  /** after the close, the session whose count isn't in yet (R8B-008) */
  pending?: Pending;
  /** earlier days whose counts a later run changed, the last week's (R13-009) */
  revised?: Revision[];
};

export type Revision = { day: string; before: { adv: number; dec: number; unch: number }; after: { adv: number; dec: number; unch: number }; at?: string };

/** One line per earlier day whose rose / fell / unchanged counts a later run changed: "8 Oct revised: 338 rose, 163 fell,
 * 1 unchanged (was 337, 163, 1)". A stock's price corrected after the day was published moves its count; the page says so
 * instead of changing a published day without a word (R13-009). */
export function revisionLines(revised: Revision[] | null | undefined, dayText: (iso: string) => string): string[] {
  const latest = new Map<string, Revision>();
  for (const r of revised ?? []) {
    const had = latest.get(r.day);
    latest.set(r.day, had ? { ...r, before: had.before } : r);   // several runs: from the first count to the last
  }
  return [...latest.values()].filter((r) => r.before.adv !== r.after.adv || r.before.dec !== r.after.dec || r.before.unch !== r.after.unch)
    .sort((a, b) => (a.day < b.day ? 1 : -1))
    .map((r) => `${dayText(r.day)} revised: ${r.after.adv} rose, ${r.after.dec} fell, ${r.after.unch} unchanged (was ${r.before.adv}, ${r.before.dec}, ${r.before.unch})`);
}

export const RANGES: [RangeId, string][] = [["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["2y", "2Y"], ["all", "All"]];

export type BreadthAlert = { id: string; group: GroupId; level: number; side: "above" | "below" | null; created_at: string; fired_at: string | null };
export type BreadthAlerts = { items: BreadthAlert[]; limit: number; channels: string[] };

export const breadthApi = {
  get: (group: GroupId, range: RangeId, brief = false) =>
    api<BreadthView>(`/invest/breadth?group=${group}&range=${range}${brief ? "&brief=true" : ""}`),
  /** Only the live card's points and the next count's note, for a page that has the rest (LIVE-1: read each minute while India trades). */
  live: (group: GroupId) => api<Pick<BreadthView, "live" | "pending">>(`/invest/breadth?group=${group}&live_only=true`),
  alerts: () => api<BreadthAlerts>("/invest/breadth/alerts"),
  addAlert: (group: GroupId, level: number) => api<BreadthAlerts>("/invest/breadth/alerts", { method: "POST", body: { group, level } }),
  deleteAlert: (id: string) => api<BreadthAlerts>(`/invest/breadth/alerts/${id}`, { method: "DELETE" }),
};



/** "1,234" for counts, "62.5%" for shares, signed changes ("+3", "−1.2 pts"). */
export const count = (v: number | null | undefined) => (v == null ? "–" : Math.round(v).toLocaleString("en-IN"));
export const share = (v: number | null | undefined) => (v == null ? "–" : `${v.toFixed(1)}%`);
export function delta(v: number | null | undefined, unit: "" | "pts" = "", dp = 0): string {
  if (v == null) return "";
  const r = Number(v.toFixed(dp));
  if (r === 0) return "no change";
  return `${r > 0 ? "+" : "−"}${Math.abs(r).toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp })}${unit ? ` ${unit}` : ""}`;
}
/** The thrust days as a list: when they span more than this year, every day carries its year, so "16 Apr 2025, 8 Apr"
 *  doesn't leave the second one's year to guess (R35). */
export function thrustDays(days: string[]): string {
  const year = String(new Date().getFullYear());
  const withYear = days.some((d) => d.slice(0, 4) !== year);
  return days.map((d) => (withYear ? fmtDate(d.slice(0, 10), { year: true }) : shortDay(d))).join(", ");
}

/** A day as "3 Oct" (and the year when it isn't this one). */
export function shortDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return fmtDate(iso, { year: d.getFullYear() !== new Date().getFullYear() });
}

/** The date under each figure of the card while it shows today's count: rose / fell and the share above the 50-day average
 * are today's, the 52-week highs and lows come with the close and are the last close's, each said with its own day (the
 * card's heading, "Today, final at 15:30", dated only the first two). Null when the figures share one day. */
export function cardDates(d: Pick<BreadthView, "today" | "live">): { counts: string; highs: string | null } | null {
  const live = d.live && (d.live.state === "live" || d.live.state === "final") && d.live.latest ? d.live : null;
  if (!live) return null;
  const sameDay = d.today?.day === live.day;
  return { counts: `Today, ${shortDay(live.day)}`, highs: d.today ? (sameDay ? `Today, ${shortDay(d.today.day)}` : `Close of ${shortDay(d.today.day)}`) : null };
}

/** What the Invest home's breadth card shows: while the market is open, the newest live count (R7T-010: the card showed
 * the 8 Oct close after 9 Oct's open while the breadth page was live); otherwise the last close's, said so. */
export function cardFigures(d: Pick<BreadthView, "today" | "live"> & { pending?: Pending }): {
  live: boolean; final?: boolean; adv: number | null; dec: number | null; pct50: number | null; highs: number | null; lows: number | null; when: string;
} | null {
  const final = d.live?.state === "final";          // after the close, until the evening's count (R28-012)
  const l = d.live && (d.live.state === "live" || final) ? d.live.latest : null;
  if (l) return { live: true, final, adv: l.adv, dec: l.dec, pct50: l.pct50, highs: null, lows: null, when: final ? `Today, final at ${d.live?.as_of} IST` : d.live?.as_of ? `Live as of ${d.live.as_of} IST` : "Live" };
  if (!d.today) return null;
  return { live: false, adv: d.today.adv.value, dec: d.today.dec.value, pct50: d.today.pct50.value, highs: d.today.highs.value,
    lows: d.today.lows.value, when: latestDue(d.today.day, d.pending) ?? `Last close, ${shortDay(d.today.day)}` };
}

/** A breadth view with a newer live card (and next-count note) laid over it, for the same group; any other view is kept as it is. */
export function withLive(cur: BreadthView | null | "error", got: Pick<BreadthView, "live" | "pending"> | null | undefined, group: string): BreadthView | null | "error" {
  if (!cur || cur === "error" || !got || cur.group.id !== group) return cur;
  return { ...cur, live: got.live ?? null, pending: got.pending ?? undefined };
}
