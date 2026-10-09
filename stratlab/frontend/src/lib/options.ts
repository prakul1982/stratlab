import { inr } from "./format";
import type { OptLeg, OptionStrategy, OptPreview, StrikePick } from "./types";

/** A premium, a profit or a loss in the options builder: whole rupees, the same everywhere (the premium collected, the
 * most it can make, and what is left after charges); paise only for a figure under ₹100, where they are the answer
 * (a spread that keeps -₹92.68 after charges). The charges themselves are small and keep their paise. */
export function optMoney(v: number | null | undefined): string {
  if (v == null) return inr(v);
  return inr(v, Math.abs(v) < 100 ? 2 : 0);
}

/** A price level (a breakeven, the spot) at the contract's own precision: whole points for an index, and a currency
 * option's quarter paise, "95.1625" (R11C-007: USDINR's breakevens of 95.16 and 97.10 read "95 and 97"). */
export function levelText(x: number, tick?: number | null): string {
  if (tick && tick < 0.01) {
    const v = Math.round(x / tick) * tick;
    return v.toLocaleString("en-IN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  }
  return Math.round(x).toLocaleString("en-IN");
}

/** The banner over a structure some of whose legs had no bid or ask to fill on (R11C-007: USDINR priced from last trades
 * hours old, under "Fills use the real bid and ask"). Empty when every leg had one. */
export function staleQuoteLine(fromLast: number, legs: number): string {
  if (!fromLast) return "";
  const lead = fromLast >= legs
    ? (legs === 1 ? "No live bid or ask: the leg is priced from its last traded price" : "No live bid or ask: every leg is priced from its last traded price")
    : `No live bid or ask for ${fromLast} of the ${legs} legs: ${fromLast === 1 ? "it is priced from its last traded price" : "they are priced from their last traded prices"}`;
  return `${lead}, which may be hours old. The numbers below can be far from what an order would fill at now.`;
}

/** The ways a leg's strike can be picked (strike rules beyond the distance are Pro). */
export const PICKS: [StrikePick, string][] = [["offset", "Distance from ATM"], ["delta", "Closest delta"], ["delta_range", "Delta range"],
  ["premium", "Premium"], ["straddle_pct", "% of ATM straddle"]];

/** A leg's strike rule in a few words: "ATM", "2 OTM", "Δ 0.20", "Δ 0.15–0.25", "₹50", "≥ ₹40", "20% of straddle". */
export function legRule(l: OptLeg, unit: "strikes" | "points"): string {
  switch (l.pick ?? "offset") {
    case "delta": return `Δ ${(l.delta ?? 0.2).toFixed(2)}`;
    case "delta_range": return `Δ ${(l.delta ?? 0.2).toFixed(2)}–${(l.deltaTo ?? 0.3).toFixed(2)}`;
    case "premium": return `${{ near: "≈", gte: "≥", lte: "≤" }[l.premiumOp ?? "near"]} ₹${l.premium ?? 50}`;
    case "straddle_pct": return `${l.pct ?? 20}% of straddle`;
    default: return l.offset === 0 ? "ATM" : `${Math.abs(l.offset)}${unit === "points" ? " pts" : ""} ${l.offset > 0 ? "OTM" : "ITM"}`;
  }
}

export const STRUCTURES: { id: string; name: string; hint: string; unit: "strikes" | "points"; legs: OptLeg[] }[] = [
  { id: "short_straddle", name: "Short straddle", hint: "Sell the at-the-money call and put", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 }] },
  { id: "short_strangle", name: "Short strangle", hint: "Sell a call and a put either side of the money", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 4, lots: 1 }, { side: "sell", opt: "PE", offset: 4, lots: 1 }] },
  { id: "iron_fly", name: "Iron fly", hint: "A short straddle with bought wings that cap the loss", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 0, lots: 1 },
      { side: "buy", opt: "CE", offset: 8, lots: 1 }, { side: "buy", opt: "PE", offset: 8, lots: 1 }] },
  { id: "iron_condor", name: "Iron condor", hint: "A short strangle with bought wings", unit: "strikes",
    legs: [{ side: "sell", opt: "CE", offset: 4, lots: 1 }, { side: "sell", opt: "PE", offset: 4, lots: 1 },
      { side: "buy", opt: "CE", offset: 8, lots: 1 }, { side: "buy", opt: "PE", offset: 8, lots: 1 }] },
  { id: "long_straddle", name: "Long straddle", hint: "Buy the at-the-money call and put for a big move", unit: "strikes",
    legs: [{ side: "buy", opt: "CE", offset: 0, lots: 1 }, { side: "buy", opt: "PE", offset: 0, lots: 1 }] },
  { id: "bull_call_spread", name: "Bull call spread", hint: "Buy a call, sell a higher one", unit: "strikes",
    legs: [{ side: "buy", opt: "CE", offset: 0, lots: 1 }, { side: "sell", opt: "CE", offset: 4, lots: 1 }] },
  { id: "bear_put_spread", name: "Bear put spread", hint: "Buy a put, sell a lower one", unit: "strikes",
    legs: [{ side: "buy", opt: "PE", offset: 0, lots: 1 }, { side: "sell", opt: "PE", offset: 4, lots: 1 }] },
  { id: "sell_call", name: "Sell a call", hint: "One sold call", unit: "strikes", legs: [{ side: "sell", opt: "CE", offset: 2, lots: 1 }] },
  { id: "sell_put", name: "Sell a put", hint: "One sold put", unit: "strikes", legs: [{ side: "sell", opt: "PE", offset: 2, lots: 1 }] },
  { id: "buy_call", name: "Buy a call", hint: "One bought call", unit: "strikes", legs: [{ side: "buy", opt: "CE", offset: 0, lots: 1 }] },
  { id: "buy_put", name: "Buy a put", hint: "One bought put", unit: "strikes", legs: [{ side: "buy", opt: "PE", offset: 0, lots: 1 }] },
];

export const POPULAR_FALLBACK = [
  { exchange: "NFO", name: "NIFTY" }, { exchange: "NFO", name: "BANKNIFTY" }, { exchange: "BFO", name: "SENSEX" },
  { exchange: "NFO", name: "FINNIFTY" }, { exchange: "MCX", name: "CRUDEOIL" }, { exchange: "CDS", name: "USDINR" },
] as const;

/** Whether a structure's name is one the builder made up ("NIFTY iron condor", "NIFTY options on 7 EMA cross") rather
 * than one the person typed: only a made-up one follows a change of strategy, underlying or rules. */
export function isAutoName(name: string, underlying: string): boolean {
  const n = name.trim();
  if (!n) return true;
  const rest = n.startsWith(`${underlying} `) ? n.slice(underlying.length + 1) : null;
  if (rest == null) return false;
  return rest === "options" || rest.startsWith("options on ") || STRUCTURES.some((s) => s.name.toLowerCase() === rest);
}

export function blankOptions(): OptionStrategy {
  const s = STRUCTURES[0];
  return {
    name: "NIFTY short straddle", structure: s.id, exchange: "NFO", underlying: "NIFTY", expiry: "current", offsetUnit: s.unit,
    legs: s.legs.map((l) => ({ ...l })),
    timing: { entry: "09:30", lastEntry: "14:45", squareoff: "15:15", maxEntries: 1, cooldown: 0 },
    risk: { stopType: "credit_pct", stop: 30, tgtType: "none", tgt: 0, trailAfter: 0, trailBy: 0, legStopPct: 0, dailyLoss: 0 },
    recenter: { enabled: false, every: 30, threshold: 2, roll: "shorts" },
    sizing: { mode: "lots", lots: 1, capital: 500000, safety: 0.98 },
    costs: { brokerage: 20, slippageTicks: 0, freeze: 0 },
    notes: "",
  };
}

/** MCX trades into the evening and currency options until 17:00; everything else follows equity hours. */
export const sessionFor = (exchange: string) =>
  exchange === "MCX" ? { entry: "09:15", lastEntry: "22:30", squareoff: "23:15" }
    : exchange === "CDS" ? { entry: "09:15", lastEntry: "16:15", squareoff: "16:45" }
      : { entry: "09:30", lastEntry: "14:45", squareoff: "15:15" };

/** A held or priced leg: its contract, units of the underlying and the price it filled at. */
export interface HeldLeg { side: "buy" | "sell"; opt: "CE" | "PE"; strike: number; qty: number; fill: number }

/** Profit at expiry with the underlying at x, before costs. */
export function atExpiry(legs: HeldLeg[], x: number): number {
  return legs.reduce((sum, l) => {
    const intrinsic = l.opt === "CE" ? Math.max(0, x - l.strike) : Math.max(0, l.strike - x);
    return sum + (l.side === "sell" ? l.fill - intrinsic : intrinsic - l.fill) * l.qty;
  }, 0);
}

/** A leg in a few words: "Sold 25,000 CE". */
export const legName = (side: "buy" | "sell", strike: number, opt: "CE" | "PE") =>
  `${side === "sell" ? "Sold" : "Bought"} ${strike.toLocaleString("en-IN")} ${opt}`;

/** Prices 10% either side of the spot: an even grid plus every strike inside it, where the payoff bends. */
export function priceGrid(spot: number, strikes: number[], n = 121): number[] {
  const lo = spot * 0.9, hi = spot * 1.1;
  return [...Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1)), ...strikes.filter((k) => k > lo && k < hi)]
    .sort((a, b) => a - b).filter((x, i, arr) => i === 0 || x !== arr[i - 1]);
}

/** A priced structure's legs, sized: each leg's lots × units × the lot size. */
export function heldLegs(p: OptPreview): HeldLeg[] {
  return p.legs.filter((l) => l.strike != null && l.fill != null)
    .map((l) => ({ side: l.side, opt: l.opt, strike: l.strike!, fill: l.fill!, qty: l.lots * p.units * p.lot }));
}

/** Profit or loss at expiry across a range of prices, for a priced structure. */
export function payoff(p: OptPreview) {
  const legs = heldLegs(p);
  const at = (x: number) => atExpiry(legs, x);
  const xs = priceGrid(p.spot, legs.map((l) => l.strike));
  const ys = xs.map(at);
  // exact bounds, as options/charges.py works them out: the payoff is straight between strikes and the price stops at
  // zero, so the extremes are at zero or a strike; only above the top strike can it run on, by the calls' net slope
  const at0 = [0, ...legs.map((l) => l.strike)], corners = at0.map(at);
  const slopeAbove = legs.reduce((n, l) => n + (l.opt === "CE" ? (l.side === "buy" ? 1 : -1) * l.qty : 0), 0);
  const maxP = Math.max(...corners), maxL = Math.min(...corners);
  const breakevens: number[] = [];
  for (let i = 1; i < xs.length; i++) if ((ys[i - 1] < 0) !== (ys[i] < 0)) breakevens.push(xs[i - 1] + ((xs[i] - xs[i - 1]) * -ys[i - 1]) / (ys[i] - ys[i - 1]));
  const credit = legs.reduce((s, l) => s + (l.side === "sell" ? 1 : -1) * l.fill * l.qty, 0);
  // the price where each bound is reached: a flat stretch (an iron condor beyond its wings) reaches it at every price
  // there, so take the one nearest today's price; "outside the chart" is then said only when no price on it reaches it
  const nearest = (v: number) => at0.filter((_, i) => Math.abs(corners[i] - v) <= 1e-6 * Math.max(1, Math.abs(v)))
    .reduce((a, b) => (Math.abs(b - p.spot) < Math.abs(a - p.spot) ? b : a));
  return { xs, ys, maxProfit: slopeAbove > 1e-9 ? null : maxP, maxLoss: slopeAbove < -1e-9 ? null : maxL, breakevens, credit,
    bestAt: nearest(maxP), worstAt: nearest(maxL) };
}

/** sessionStorage key: an imported options strategy handed from the import dialog to the Options page. */
export const IMPORTED = "stratlab.options.import";

/** The line a flat options session shows after a trade closed while the rules' gap between trades still runs (R7T-013: after
 * a 09:41 stop-out with entries 120 minutes apart, "Entries open until 14:45" instead of the next entry's time). Null when
 * no gap is running at `now`; `lastEntry` is the day's last entry and `entry` the first. */
export function gapLine(a: { cool_until?: string | null; next_entry?: string | null }, cooldown: number | null | undefined, lastEntry: string, entry: string,
  now: Date): string | null {
  if (!a.cool_until) return null;
  const until = new Date(a.cool_until);
  if (Number.isNaN(until.getTime()) || until.getTime() <= now.getTime()) return null;
  const gap = cooldown ? `entries are ${cooldown} min apart` : "the rules keep a gap between entries";
  return a.next_entry ? `Next entry from ${a.next_entry}: ${gap}.` : `Next entry ${entry} on the next market day: ${gap}, past the last entry at ${lastEntry}.`;
}
