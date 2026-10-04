/* Option pricing for the what-if sliders: a port of the backend's options/greeks.py (Black's 1976 formula on the
 * forward, the Greeks, and a position valued with the underlying moved, IV shifted and days passed), so the curve and
 * the Greeks move as a slider does without a round trip. The server solves each option's IV from its bid-ask middle and
 * sends the model's inputs; this only re-prices under them. Checked against fixtures the backend writes
 * (unit/greeks.test.mjs). Kept free of imports so Node can run the tests on this file directly.
 *
 * Model estimates, labelled as such wherever they're shown: real prices can differ. */

export type OptKind = "CE" | "PE";

/** The inputs one expiry's options share, as /options/preview, /options/chain and /options/greeks send them. */
export interface GreekModel {
  expiry: string; spot: number; forward: number; basis: number; forward_from: "parity" | "spot"; atm: number | null;
  t: number; days: number; rate: number; atm_iv: number | null; as_of: string;
}
/** One option's IV and Greeks (per option): delta and gamma per point, theta per day, vega per vol point. */
export interface OptionGreeks {
  mid: number | null; iv: number | null; iv_from: "price" | "atm" | null;
  delta?: number; gamma?: number; theta?: number; vega?: number; model_price?: number;
}
/** A leg the what-if can re-price: qty in units of the underlying, fill the price paid or received, iv a fraction,
 * t the years left now, basis the forward over the spot now. */
export interface ModelLeg { side: "buy" | "sell"; opt: OptKind; strike: number; qty: number; fill: number; iv: number; t: number; basis: number }
export interface NetGreeks { delta: number; gamma: number; theta: number; vega: number }
export interface Scenario extends NetGreeks { pnl: number; value: number }
export interface WhatIf { spotPct: number; ivShift: number; days: number }

export const MIN_VOL = 0.005;      // a what-if IV shift can't take an option below 0.5% volatility
export const NO_MOVE: WhatIf = { spotPct: 0, ivShift: 0, days: 0 };

const SQRT_PI = Math.sqrt(Math.PI);

/** erfc for z ≥ 0, to a few parts in 1e16: a series below 3, a continued fraction above. */
function erfc(z: number): number {
  if (z < 3) {
    let term = z, sum = z;
    for (let n = 1; n < 200; n++) {
      term *= (2 * z * z) / (2 * n + 1);
      sum += term;
      if (term < sum * 1e-17) break;
    }
    return 1 - (2 / SQRT_PI) * Math.exp(-z * z) * sum;
  }
  let f = z;
  for (let n = 60; n >= 1; n--) f = z + n / 2 / f;
  return Math.exp(-z * z) / (SQRT_PI * f);
}

/** The standard normal distribution function. */
export function ncdf(x: number): number {
  const z = Math.abs(x) / Math.SQRT2;
  const tail = 0.5 * erfc(z);
  return x >= 0 ? 1 - tail : tail;
}

export function npdf(x: number): number {
  return Math.exp((-x * x) / 2) / Math.sqrt(2 * Math.PI);
}

/** An option's price on a forward `f`, discounted at `r` for `t` years. At or past expiry: the intrinsic value. */
export function black76(f: number, k: number, t: number, sigma: number, kind: OptKind, r = 0): number {
  if (t <= 0 || sigma <= 0) return kind === "CE" ? Math.max(0, f - k) : Math.max(0, k - f);
  const sd = sigma * Math.sqrt(t);
  const d1 = (Math.log(f / k) + (sd * sd) / 2) / sd, d2 = d1 - sd;
  const disc = Math.exp(-r * t);
  return disc * (kind === "CE" ? f * ncdf(d1) - k * ncdf(d2) : k * ncdf(-d2) - f * ncdf(-d1));
}

/** Price and Greeks of one option (delta and gamma per point of the forward, theta per calendar day, vega per vol
 * point). At or past expiry: the intrinsic value, delta 1, 0 or −1, and nothing else. */
export function greeks(f: number, k: number, t: number, sigma: number, kind: OptKind, r: number) {
  const price = black76(f, k, t, sigma, kind, r);
  if (t <= 0 || sigma <= 0) {
    const itm = kind === "CE" ? f > k : f < k;
    return { price, delta: itm ? (kind === "CE" ? 1 : -1) : 0, gamma: 0, theta: 0, vega: 0 };
  }
  const sd = sigma * Math.sqrt(t);
  const d1 = (Math.log(f / k) + (sd * sd) / 2) / sd;
  const disc = Math.exp(-r * t), n1 = npdf(d1);
  return {
    price,
    delta: kind === "CE" ? disc * ncdf(d1) : -disc * ncdf(-d1),
    gamma: (disc * n1) / (f * sd),
    theta: (r * price - (disc * f * n1 * sigma) / (2 * Math.sqrt(t))) / 365,
    vega: (disc * f * n1 * Math.sqrt(t)) / 100,
  };
}

/** [forward, years left, volatility] for a leg with the underlying at `spot`, `days` on and IV moved `ivShift` vol
 * points. The forward keeps its ratio to the spot, shrinking towards 1 as expiry nears. */
export function legInputs(leg: ModelLeg, spot: number, days = 0, ivShift = 0): [number, number, number] {
  const t = leg.t - days / 365;
  if (t <= 1e-12) return [spot, 0, 0];
  const b = leg.t > 0 ? leg.basis ** (t / leg.t) : 1;
  return [spot * b, t, Math.max(MIN_VOL, leg.iv + ivShift / 100)];
}

/** The position's model profit before charges (value less what was paid) and its net Greeks, in rupees. */
export function scenario(legs: ModelLeg[], spot: number, days: number, ivShift: number, r: number): Scenario {
  const out: Scenario = { pnl: 0, value: 0, delta: 0, gamma: 0, theta: 0, vega: 0 };
  for (const lg of legs) {
    const [f, t, sigma] = legInputs(lg, spot, days, ivShift);
    const g = greeks(f, lg.strike, t, sigma, lg.opt, r);
    const n = (lg.side === "buy" ? 1 : -1) * lg.qty;
    out.value += n * g.price;
    out.pnl += n * (g.price - lg.fill);
    out.delta += n * g.delta; out.gamma += n * g.gamma; out.theta += n * g.theta; out.vega += n * g.vega;
  }
  return out;
}

/** The position's model profit with the underlying at each price in `xs`. */
export function curve(legs: ModelLeg[], xs: number[], days: number, ivShift: number, r: number): number[] {
  return xs.map((x) => scenario(legs, x, days, ivShift, r).pnl);
}

/** Each leg's own Greeks (per option) under the what-if, for the leg table. */
export function legGreeks(leg: ModelLeg, spot: number, w: WhatIf, r: number) {
  const [f, t, sigma] = legInputs(leg, spot * (1 + w.spotPct / 100), w.days, w.ivShift);
  return { ...greeks(f, leg.strike, t, sigma, leg.opt, r), iv: sigma, t };
}
