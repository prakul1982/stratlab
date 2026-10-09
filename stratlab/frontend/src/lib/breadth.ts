import { api } from "./api";
import type { LiveView } from "./breadthLive";
import { fmtDate, latestDue, type Pending } from "./format";
export { liveSeries, liveTitle } from "./breadthLive";
export { BROAD_GROUP, MARKET_GROUP, groupRegion, savePick, savedPick } from "./breadthPick";
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
export type SectorTable = { columns: { label: string; day: string }[]; rows: { sector: string; stocks: number; values: (number | null)[] }[] };
export type BreadthView = {
  group: Group; groups: Group[]; today: Today | null; as_of: string | null; since: string | null; range: RangeId;
  help: Record<string, string>; status: string | null; locked: boolean; plan_needed: string;
  history: History | null; sectors: SectorTable | null; thrusts: string[] | null; live: LiveView | null;
  /** after the close, the session whose count isn't in yet (R8B-008) */
  pending?: Pending;
};

export const RANGES: [RangeId, string][] = [["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["2y", "2Y"], ["all", "All"]];

export type BreadthAlert = { id: string; group: GroupId; level: number; side: "above" | "below" | null; created_at: string; fired_at: string | null };
export type BreadthAlerts = { items: BreadthAlert[]; limit: number; channels: string[] };

export const breadthApi = {
  get: (group: GroupId, range: RangeId, brief = false) =>
    api<BreadthView>(`/invest/breadth?group=${group}&range=${range}${brief ? "&brief=true" : ""}`),
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
/** A day as "3 Oct" (and the year when it isn't this one). */
export function shortDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return fmtDate(iso, { year: d.getFullYear() !== new Date().getFullYear() });
}

/** What the Invest home's breadth card shows: while the market is open, the newest live count (R7T-010: the card showed
 * the 8 Oct close after 9 Oct's open while the breadth page was live); otherwise the last close's, said so. */
export function cardFigures(d: Pick<BreadthView, "today" | "live"> & { pending?: Pending }): {
  live: boolean; adv: number | null; dec: number | null; pct50: number | null; highs: number | null; lows: number | null; when: string;
} | null {
  const l = d.live?.state === "live" ? d.live.latest : null;
  if (l) return { live: true, adv: l.adv, dec: l.dec, pct50: l.pct50, highs: null, lows: null, when: d.live?.as_of ? `Live as of ${d.live.as_of} IST` : "Live" };
  if (!d.today) return null;
  return { live: false, adv: d.today.adv.value, dec: d.today.dec.value, pct50: d.today.pct50.value, highs: d.today.highs.value,
    lows: d.today.lows.value, when: latestDue(d.today.day, d.pending) ?? `Last close, ${shortDay(d.today.day)}` };
}
