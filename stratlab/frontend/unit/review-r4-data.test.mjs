import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// Round 4, the data builder: an ETF's gap from the price beside it, axis labels that tell the truth, one reading of a
// company's price, no run of empty months, and the filings link.

const etf = (over = {}) => ({ symbol: "NIFTYBEES", name: "Nifty BeES", underlying: null, fund: "equity", fund_label: "Equity ETF", price: 270.5,
  price_at: "2026-10-07T15:30+05:30", inav: null, inav_gap: null, nav: 269.8, nav_date: "2026-10-07", nav_gap: 0.26, gap: 0.26, basis: "NAV",
  text: "NIFTYBEES trades 0.26% above its last NAV", ...over });

test("an ETF's badge is worked out from the price shown in the same row (R4-005)", async () => {
  const { gapAtPrice } = await import("../src/lib/etfGapMath.ts");
  const row = gapAtPrice(etf(), 270.06, "2026-10-07");     // a price of the NAV's own day (R5O-005)
  assert.equal(row.price, 270.06);
  assert.equal(row.nav_gap, 0.1);                       // 270.06 / 269.80 - 1, not the list's 270.50
  assert.equal(row.gap, 0.1);
  assert.equal(row.basis, "NAV");
  assert.equal(row.price_at, null);                     // not "as of" the list's read
  assert.match(row.text, /^NIFTYBEES trades 0\.10% above its last NAV$/);
  // the same row and the same price: the list's own figure
  assert.equal(gapAtPrice(etf(), 270.5, "2026-10-07").gap, 0.26);
  // an indicative NAV, when a source gives one, is the basis (as in the list)
  const withInav = gapAtPrice(etf({ inav: 270.0 }), 270.06);
  assert.equal(withInav.basis, "iNAV");
  assert.equal(withInav.inav_gap, 0.02);
  // no usable price: the row as the list has it; a NAV of another unit is no gap
  assert.equal(gapAtPrice(etf(), null).gap, 0.26);
  assert.equal(gapAtPrice(etf(), 0).gap, 0.26);
  const far = gapAtPrice(etf(), 900, "2026-10-07");
  assert.equal(far.gap, null);
  assert.equal(far.basis, null);
});

test("axis labels read the number at their tick: 22.5 is never labelled 23% (R4-019)", async () => {
  const { honestTicks, distinctTicks } = await import("../src/lib/chartFormat.ts");
  const whole = (v) => `${v.toFixed(0)}%`;
  const ticks = honestTicks(16.9, 26.1, 4, whole);        // the FII chart's range: 2.5 apart would read 18, 20, 23, 25
  for (const t of ticks) assert.ok(Number.isInteger(t), `${t} is not a whole number`);
  const steps = new Set(ticks.slice(1).map((t, i) => +(t - ticks[i]).toFixed(6)));
  assert.equal(steps.size, 1, "the ticks are evenly spaced");
  assert.ok(ticks.length >= 3);
  // a formatter that shows the decimal keeps the 2.5 step
  const one = (v) => `${+v.toFixed(1)}%`;
  assert.deepEqual(honestTicks(16.9, 26.1, 4, one), [17.5, 20, 22.5, 25]);
  // nothing changes when the labels already agree with the ticks
  assert.deepEqual(honestTicks(0, 100, 5, whole), [0, 20, 40, 60, 80, 100]);
  const [kept, labels] = distinctTicks(ticks, whole);
  assert.equal(kept.length, labels.length);
});

test("the chart's newest candle is the price the page shows (R4-011)", async () => {
  const { settleLast } = await import("../src/charts/price/settle.ts");
  const candles = [{ t: "2026-10-07T00:00:00+05:30", o: 3050, h: 3070, l: 3040, c: 3050 }, { t: "2026-10-08T00:00:00+05:30", o: 3050, h: 3062.2, l: 3025.6, c: 3038.03 }];
  const read = { price: 3037.97, asOf: "2026-10-08T10:25+05:30", tz: "Asia/Kolkata" };
  const got = settleLast(candles, read);
  assert.equal(got[1].c, 3037.97);
  assert.equal(got[0].c, 3050);
  assert.equal(got[1].h, 3062.2);
  assert.equal(got[1].l, 3025.6);
  assert.equal(candles[1].c, 3038.03, "the source's candles are not changed in place");
  // a price outside the candle's range widens it
  assert.equal(settleLast(candles, { ...read, price: 3070 })[1].h, 3070);
  // a price read on another day than the newest candle, or none, leaves the candles as sent
  assert.equal(settleLast(candles, { ...read, asOf: "2026-10-09T10:25+05:30" }), candles);
  assert.equal(settleLast(candles, { ...read, price: null }), candles);
  assert.equal(settleLast([], read).length, 0);
  // a daily candle written as a plain date
  assert.equal(settleLast([{ t: "2026-10-08", c: 1 }], { price: 2, asOf: "2026-10-08T09:30-04:00", tz: "America/New_York" })[0].c, 2);
});

test("runs of months nobody filed anything for fold into one row (R4-013)", async () => {
  const { foldEmptyMonths } = await import("../src/lib/biz.ts");
  const months = ["2026-09", "2026-08", "2026-07", "2026-06", "2026-05", "2026-04", "2026-03", "2025-09"];
  const has = (p) => p === "2026-09" || p === "2025-09" || p === "2026-06";
  assert.deepEqual(foldEmptyMonths(months, has), ["2026-09", "gap:2026-08:2026-07:2", "2026-06", "gap:2026-05:2026-03:3", "2025-09"]);
  // one empty month between two filed ones stays a row of its own
  assert.deepEqual(foldEmptyMonths(["2026-09", "2026-08", "2026-07"], (p) => p !== "2026-08"), ["2026-09", "2026-08", "2026-07"]);
  assert.deepEqual(foldEmptyMonths([], () => false), []);
  assert.deepEqual(foldEmptyMonths(["2026-09", "2026-08"], () => false), ["gap:2026-09:2026-08:2"]);
});
