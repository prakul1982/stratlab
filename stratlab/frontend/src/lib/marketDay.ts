import { hm, wall } from "./marketHours";
import type { Market } from "./types";

// Apart from marketHours on purpose: that file is in the download every page shares (the landing page's too, which has a size
// budget); only the Markets panel asks which day a market last traded.

/** The last day the market traded, as a date in the exchange's own calendar ("2026-11-06"): today once today's session has opened,
 * else the nearest earlier day that is neither a weekend day nor one of the exchange's holidays. Null for a market that never shuts
 * (crypto). Forex and the global commodity futures trade from Sunday evening to Friday 17:00 New York time, so a Saturday, and a
 * Sunday before the open, is Friday's (and from that open it is Monday's session). What a "last close" label says (owner, 9 Nov: Market Watch said "last close Sun"). */
export function lastTradingDay(m: Market, now = new Date()): string | null {
  if (m.id === "CRYPTO") return null;
  if (m.id === "FX" || !m.hours?.open || !m.hours?.close) {
    const w = wall(now, "America/New_York");
    const sunOpen = (m.id === "CMDTY" ? 18 : 17) * 60;
    // the session that opens on Sunday evening is Monday's
    return w.iso(w.wd === 6 ? -1 : w.wd === 0 ? (w.min < sunOpen ? -2 : 1) : 0);
  }
  const w = wall(now, m.tz), shut = new Set(m.holidays ?? []);
  const trades = (n: number) => { const d = (((w.wd + n) % 7) + 7) % 7; return d >= 1 && d <= 5 && !shut.has(w.iso(n)); };
  let n = trades(0) && w.min >= hm(m.hours.open) ? 0 : -1;
  while (!trades(n) && n > -30) n--;
  return w.iso(n);
}
