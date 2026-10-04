// The what-if pricing against the backend's own answers (fixtures/greeks.json, written by
// stratlab/backend/tests/test_greeks.py from app/options/greeks.py). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as G from "../src/lib/greeks.ts";

const fx = JSON.parse(readFileSync(new URL("./fixtures/greeks.json", import.meta.url), "utf8"));
const close = (got, want, what, rel = 1e-9, abs = 1e-9) =>
  assert.ok(Math.abs(got - want) <= Math.max(abs, rel * Math.abs(want)), `${what}: ${got} vs ${want}`);

test("the IV floor matches the backend's", () => {
  assert.equal(G.MIN_VOL, fx.min_vol);
});

test("the normal distribution matches the backend's erf to 1e-15", () => {
  // values of Φ from the backend's math.erf, worked out once: the far tails are where a cheap approximation fails
  for (const [x, want] of [[0, 0.5], [1, 0.8413447460685429], [-2.5, 0.006209665325776159], [4.2, 0.9999866542509841], [-6, 9.865876449133282e-10]])
    close(G.ncdf(x), want, `ncdf(${x})`, 1e-12, 1e-15);
});

test(`${fx.prices.length} option prices and Greeks match the backend`, () => {
  for (const c of fx.prices) {
    const g = G.greeks(c.f, c.k, c.t, c.sigma, c.kind, c.r);
    const what = `${c.kind} f=${c.f} k=${c.k} t=${c.t} s=${c.sigma} r=${c.r}`;
    close(g.price, c.price, `${what} price`, 1e-9, 1e-10);
    for (const k of ["delta", "gamma", "theta", "vega"]) close(g[k], c[k], `${what} ${k}`, 1e-8, 1e-12);
  }
});

for (const p of fx.positions) {
  test(`${p.name}: the position under every what-if matches the backend`, () => {
    for (const c of p.cases) {
      const s = G.scenario(p.legs, p.spot * (1 + c.spot_pct / 100), c.days, c.iv_shift, fx.rate);
      const what = `${p.name} ${c.spot_pct}% ${c.days}d ${c.iv_shift}pts`;
      for (const k of ["pnl", "value", "delta", "gamma", "theta", "vega"]) close(s[k], c[k], `${what} ${k}`, 1e-8, 1e-7);
    }
    const ys = G.curve(p.legs, p.curve.xs, p.curve.days, p.curve.iv_shift, fx.rate);
    ys.forEach((y, i) => close(y, p.curve.ys[i], `${p.name} curve[${i}]`, 1e-8, 1e-7));
  });
}
