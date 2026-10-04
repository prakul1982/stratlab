// Candle transforms: reading times, Heikin-Ashi, weekly and monthly candles, and live merges. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { aggregate, heikinAshi, merge, parseTime, toBars, indexAtOrBefore } from "../src/charts/price/transforms.ts";

test("times keep the exchange's wall clock", () => {
  const [t, w] = parseTime("2024-03-05T09:15:00+05:30");
  assert.equal(t, Date.UTC(2024, 2, 5, 3, 45));
  assert.equal(new Date(w).getUTCHours(), 9);
  assert.equal(parseTime("2024-03-05")[0], Date.UTC(2024, 2, 5));
  assert.equal(parseTime("nope"), null);
});

test("candles are cleaned: sorted, one per time, missing prices filled", () => {
  const bars = toBars([{ t: "2024-01-03", c: 3 }, { t: "2024-01-02", o: 2, h: 1, l: 5, c: 2.5, v: -4 }, { t: "2024-01-03", c: 4 }, { t: "x", c: 1 }, { t: "2024-01-04", c: null }]);
  assert.equal(bars.length, 2);
  assert.deepEqual([bars[0].h, bars[0].l, bars[0].v], [2.5, 2, 0]);     // high/low wrap the open and close
  assert.equal(bars[1].c, 4);
});

test("Heikin-Ashi: close is the average price, open the middle of the previous candle", () => {
  const bars = toBars([
    { t: "2024-01-01", o: 10, h: 12, l: 9, c: 11 },
    { t: "2024-01-02", o: 11, h: 15, l: 10, c: 14 },
    { t: "2024-01-03", o: 14, h: 14.5, l: 8, c: 9 },
  ]);
  const ha = heikinAshi(bars);
  assert.deepEqual(ha.map((b) => b.c), [10.5, 12.5, 11.375]);
  assert.deepEqual(ha.map((b) => b.o), [10.5, 10.5, 11.5]);
  assert.deepEqual(ha.map((b) => b.h), [12, 15, 14.5]);
  assert.deepEqual(ha.map((b) => b.l), [9, 10, 8]);
  assert.equal(ha[0].t, bars[0].t);
});

test("weekly and monthly candles from daily ones", () => {
  // Mon 1 Jan 2024 .. Wed 10 Jan, and 1 Feb
  const days = ["2024-01-01", "2024-01-02", "2024-01-05", "2024-01-08", "2024-01-10", "2024-02-01"];
  const bars = toBars(days.map((t, i) => ({ t: `${t}T00:00:00+05:30`, o: 10 + i, h: 20 + i, l: 5 - i, c: 11 + i, v: 100 })));
  const wk = aggregate(bars, "week");
  assert.equal(wk.length, 3);
  assert.deepEqual([wk[0].o, wk[0].h, wk[0].l, wk[0].c, wk[0].v], [10, 22, 3, 13, 300]);
  const mo = aggregate(bars, "month");
  assert.equal(mo.length, 2);
  assert.deepEqual([mo[0].o, mo[0].c, mo[0].v], [10, 15, 500]);
});

test("live merges patch the last candle or append, and start over when history changes", () => {
  const a = toBars([{ t: "2024-01-01", c: 1 }, { t: "2024-01-02", c: 2 }]);
  assert.equal(merge(a, toBars([{ t: "2024-01-02", c: 2 }])).kind, "same");
  assert.equal(merge(a, toBars([{ t: "2024-01-02", c: 2.5 }])).kind, "patch");
  const app = merge(a, toBars([{ t: "2024-01-02", c: 2 }, { t: "2024-01-03", c: 3 }]));
  assert.equal(app.kind, "append");
  assert.equal(app.bars.length, 3);
  assert.equal(merge(a, toBars([{ t: "2024-01-01", c: 9 }, { t: "2024-01-02", c: 2 }])).kind, "reset");
  assert.equal(indexAtOrBefore(a, a[1].t + 5), 1);
  assert.equal(indexAtOrBefore(a, a[0].t - 5), -1);
});
