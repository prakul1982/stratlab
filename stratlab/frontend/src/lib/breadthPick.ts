import { isPeriod } from "./period";
import type { GroupId } from "./breadth";

/* The breadth group a reader opens on and the one they last picked, per market. Only `period` imported, so the unit
 * tests load this file alone. */

const KEY = "stratlab.breadth";
const DEFAULT_GROUP: GroupId = "nifty500";
/** Each market's own group to open on (R6O-007: an India reader landed on the S&P 500), and the broad one to show while
 * it has no counts yet. */
export const MARKET_GROUP: Record<"IN" | "US", GroupId> = { IN: "nifty500", US: "sp500" };
export const BROAD_GROUP: Record<"IN" | "US", GroupId> = { IN: "nse_all", US: "us_large" };
export const groupRegion = (g: GroupId): "IN" | "US" => (g === "us_large" || g === "sp500" ? "US" : "IN");

/** The group and range last picked on this device, for a market: the group last picked for that market, else the
 * market's own group (`picked` says whether the reader chose it). Without a market, the last group picked anywhere. */
export function savedPick(region?: "IN" | "US"): { group: GroupId; range: string; picked: boolean } {
  let v: { group?: GroupId; range?: string; groups?: Partial<Record<"IN" | "US", GroupId>> } = {};
  try { v = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { /* storage off */ }
  const range = isPeriod(v.range ?? "") ? v.range! : "1y";
  if (!region) return { group: v.group || DEFAULT_GROUP, range, picked: !!v.group };
  const mine = v.groups?.[region] ?? (v.group && groupRegion(v.group) === region ? v.group : undefined);
  return { group: mine ?? MARKET_GROUP[region], range, picked: !!mine };
}
export function savePick(group: GroupId, range: string) {
  try {
    let v: { groups?: Partial<Record<"IN" | "US", GroupId>> } = {};
    try { v = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { /* a broken value is replaced */ }
    localStorage.setItem(KEY, JSON.stringify({ group, range, groups: { ...(v.groups ?? {}), [groupRegion(group)]: group } }));
  } catch { /* storage off */ }
}
