/* When a dated event has happened, by India's clock. Pure, so the unit tests can read it. */
import type { EvKind, MarketEvent } from "./marketEvents";

/** The time of day in India, "18:02": what a dated event's "15:30" is compared with. */
export const istHm = (at: Date = new Date()): string =>
  at.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false });

/** An event of today whose time has passed by India's clock (a release out already counts too): no longer "coming up"
 * (R70-001: Monday's 15:30 NIFTY expiry was "Next up" at 18:00). One without a time (a holiday) lasts the day. */
export function happened(e: { date: string; time: string | null; status?: string }, today: string, nowHm: string): boolean {
  if (e.date !== today) return e.date < today;
  return e.status === "released" || (!!e.time && e.time <= nowHm);
}

/** The kinds of market event every "Coming up" lists; expiries come as the nearest weekly of each index. */
export const COMING_KINDS: EvKind[] = ["holiday", "rbi", "india", "us", "budget", "index"];

/** The market events ahead, as every "Coming up" lists them (LIVE3-015: the Invest home kept one expiry and left out a holiday
 * that My space listed): those not yet happened up to `end`, of COMING_KINDS, and the nearest weekly expiry of each index within
 * a week (R52-013, R64-008: Monday's NIFTY and Thursday's SENSEX weeklies). For the US market only the US's own events. In date order. */
export function comingMarketEvents(events: MarketEvent[], o: { today: string; nowHm: string; end: string; weekEnd: string; region?: "IN" | "US" }): MarketEvent[] {
  const sorted = [...events].sort((a, b) => a.date.localeCompare(b.date) || (a.time ?? "").localeCompare(b.time ?? ""));
  const named = new Set<string>();
  const weekly = new Set<MarketEvent>();
  for (const e of sorted)
    if (e.kind === "expiry" && /weekly/i.test(e.title) && !happened(e, o.today, o.nowHm) && e.date <= o.weekEnd && !named.has(e.title)) { named.add(e.title); weekly.add(e); }
  return sorted.filter((e) => !happened(e, o.today, o.nowHm) && e.date <= o.end && (COMING_KINDS.includes(e.kind) || weekly.has(e))
    && (o.region !== "US" || e.kind === "us"));
}
