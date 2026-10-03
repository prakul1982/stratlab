import type { OptLeg, OptionStrategy, OptPreview } from "./types";

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

/** Profit or loss at expiry across a range of prices, for a priced structure. */
export function payoff(p: OptPreview) {
  const legs = p.legs.filter((l) => l.strike != null && l.fill != null);
  const qty = (l: (typeof legs)[number]) => l.lots * p.units * p.lot;
  const at = (x: number) => legs.reduce((sum, l) => {
    const intrinsic = l.opt === "CE" ? Math.max(0, x - l.strike!) : Math.max(0, l.strike! - x);
    return sum + (l.side === "sell" ? l.fill! - intrinsic : intrinsic - l.fill!) * qty(l);
  }, 0);
  const lo = p.spot * 0.9, hi = p.spot * 1.1, n = 121;
  // an even grid plus every strike, where the line bends
  const xs = [...Array.from({ length: n }, (_, i) => lo + ((hi - lo) * i) / (n - 1)), ...legs.map((l) => l.strike!).filter((k) => k > lo && k < hi)]
    .sort((a, b) => a - b).filter((x, i, arr) => i === 0 || x !== arr[i - 1]);
  const ys = xs.map(at);
  // unlimited when the line is still sloping at the edges of a very wide range
  const far = (x: number) => at(x);
  const slopeUp = far(p.spot * 3) - far(p.spot * 2.5), slopeDown = far(p.spot * 0.05) - far(p.spot * 0.1);
  const maxP = Math.max(...ys), maxL = Math.min(...ys);
  const breakevens: number[] = [];
  for (let i = 1; i < xs.length; i++) if ((ys[i - 1] < 0) !== (ys[i] < 0)) breakevens.push(xs[i - 1] + ((xs[i] - xs[i - 1]) * -ys[i - 1]) / (ys[i] - ys[i - 1]));
  const credit = legs.reduce((s, l) => s + (l.side === "sell" ? 1 : -1) * l.fill! * qty(l), 0);
  return { xs, ys, maxProfit: slopeUp > 1e-6 || slopeDown > 1e-6 ? null : maxP, maxLoss: slopeUp < -1e-6 || slopeDown < -1e-6 ? null : maxL,
    breakevens, credit };
}

/** sessionStorage key: an imported options strategy handed from the import dialog to the Options page. */
export const IMPORTED = "stratlab.options.import";
