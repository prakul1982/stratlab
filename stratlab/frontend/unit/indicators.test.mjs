// The chart's indicator maths against the backend engine's own answers (fixtures/indicators.json, written by
// stratlab/backend/tests/test_price_chart.py from app/engine/indicators.py). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as I from "../src/charts/price/indicators.ts";
import { toBars } from "../src/charts/price/transforms.ts";

const fx = JSON.parse(readFileSync(new URL("./fixtures/indicators.json", import.meta.url), "utf8"));
const daily = toBars(fx.daily), intraday = toBars(fx.intraday);

function compute(t, p, m, bars, intra) {
  const c = bars.map((b) => b.c);
  switch (t) {
    case "sma": return I.sma(c, p);
    case "ema": return I.ema(c, p);
    case "rsi": return I.rsi(c, p);
    case "macd": return I.macd(c, p, m).line;
    case "macd_signal": return I.macd(c, p, m).signal;
    case "macd_hist": return I.macd(c, p, m).hist;
    case "bb_upper": return I.bollinger(c, p, m).upper;
    case "bb_mid": return I.bollinger(c, p, m).mid;
    case "bb_lower": return I.bollinger(c, p, m).lower;
    case "vwap": return I.vwap(bars, p, intra);
    case "supertrend": return I.supertrend(bars, p, m);
    case "stage": return I.stage(c, p, m);
  }
  throw new Error(`no port of ${t}`);
}

for (const k of fx.cases) {
  test(`${k.t}(${k.p}${k.m != null ? `, ${k.m}` : ""})${k.intraday ? " intraday" : ""} matches the engine`, () => {
    const bars = k.intraday ? intraday : daily;
    const got = compute(k.t, k.p, k.m, bars, k.intraday);
    assert.equal(got.length, k.values.length);
    k.values.forEach((want, i) => {
      if (want === null) { assert.ok(!Number.isFinite(got[i]), `${k.t}[${i}] should be blank, got ${got[i]}`); return; }
      assert.ok(Math.abs(got[i] - want) <= 1e-6 * Math.max(1, Math.abs(want)), `${k.t}[${i}]: ${got[i]} vs ${want}`);
    });
  });
}

test("the 52-week high and low only look back a year", () => {
  const bars = [{ h: 5, l: 4 }, { h: 9, l: 1 }, { h: 6, l: 5 }, { h: 7, l: 6 }].map((b) => ({ ...b, o: 0, c: 0, v: 0 }));
  const day = 86_400_000;
  const { high, low } = I.rangeHighLow(bars, [0, 1, 400, 401].map((d) => d * day), 365 * day);
  assert.deepEqual(high, [5, 9, 6, 7]);
  assert.deepEqual(low, [4, 1, 5, 5]);
});
