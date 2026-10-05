import type { Instrument } from "./types";

type Freq = "daily" | "weekly" | "monthly";

/** The SIP test, opened with an Indian stock or ETF already chosen; null for anything else (the test takes only those). */
export function sipTestLink(inst: Pick<Instrument, "symbol" | "market" | "type"> | null | undefined): string | null {
  if (!inst || inst.market !== "IN" || (inst.type !== "EQ" && inst.type !== "ETF")) return null;
  return `/money/sip-test?symbol=${encodeURIComponent(inst.symbol)}`;
}

/** Whitelisted SIP test settings from a link's query: anything unrecognised is left at the page's default. */
export function sipParams(q: URLSearchParams): { amount?: string; freq?: Freq; years?: string } {
  const out: { amount?: string; freq?: Freq; years?: string } = {};
  const amount = Number(q.get("amount"));
  if (Number.isFinite(amount) && amount > 0 && amount <= 1e8) out.amount = String(Math.round(amount));
  const freq = q.get("freq");
  if (freq === "daily" || freq === "weekly" || freq === "monthly") out.freq = freq;
  const years = Number(q.get("years"));
  if (Number.isInteger(years) && years >= 1 && years <= 10) out.years = String(years);
  return out;
}
