import type { OptLeg, OptionStrategy, OptPreview, StrikePick } from "./types";

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
  return { xs, ys, maxProfit: slopeAbove > 1e-9 ? null : maxP, maxLoss: slopeAbove < -1e-9 ? null : maxL, breakevens, credit,
    bestAt: at0[corners.indexOf(maxP)], worstAt: at0[corners.indexOf(maxL)] };   // the price where each bound is reached
}

/** sessionStorage key: an imported options strategy handed from the import dialog to the Options page. */
export const IMPORTED = "stratlab.options.import";
