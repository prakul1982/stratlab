// Review 3i (frontend): the compare page names every change (direction both ways, most in one trade, product, short
// exit) and counts checks as other pages do; the chart's RSI of a flat series is 50 as the engine's; its 52-week line on
// daily candles is the rule's own (the previous 252 candles, the candle itself left out).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import * as I from "../src/charts/price/indicators.ts";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

// "What changed" moved to src/lib/compare.ts (review 5b: stops in their own units, each run's currency, no raw codes);
// these two now run it
const C = await import("../src/lib/compare.ts");
const R = await import("../src/lib/rules.ts");
const run = (over = {}, risk = {}) => ({ strategy: { ...R.blankStrategy(), ...over, risk: { ...R.blankStrategy().risk, ...risk } }, instrument: { symbol: "NIFTY 50", currency: "INR" }, days: 365 });

test("the compare page writes a direction of both ways as itself, not long", () => {
  assert.deepEqual(C.changes(run({ side: "long" }), run({ side: "both" })), ["Direction: long only → both ways"]);
  assert.deepEqual(C.changes(run({ side: "short" }), run({ side: "both" })), ["Direction: short only → both ways"]);
  assert.match(read("src/pages/CompareExperiments.tsx"), /import \{ changes(?:, \w+)* \} from "\.\.\/lib\/compare";/);
});

test("the compare page lists most in one trade, the product and the short exit among the changes", () => {
  assert.deepEqual(C.changes(run({}, { maxAlloc: 100 }), run({}, { maxAlloc: 40 })), ["Most in one trade: 100% → 40%"]);
  assert.deepEqual(C.changes(run({ product: "auto" }), run({ product: "intraday" })), ["Indian stock costs: automatic → intraday (MIS)"]);
  const exit = [{ l: { t: "price" }, op: "xa", r: { t: "sma", p: 20 } }];
  assert.deepEqual(C.changes(run({ side: "both", shortExit: [] }), run({ side: "both", shortExit: exit })), ["Short exit: none → Price crosses above SMA 20"]);
});

test("the compare page counts the checks out of four like the other pages, as a count in its cell (DA-031)", async () => {
  const src = read("src/pages/CompareExperiments.tsx");
  assert.match(src, /\["Checks passed", \(e\) => checksCell\(e\.verdict\.passed, e\.verdict\.total\)/);
  const { checksCell } = await import("../src/lib/tradeUi.ts");
  assert.equal(checksCell(2, 4), "2 of 4");
  assert.equal(checksCell(3, 3), "3 of 4 (1 not run)");
});

test("RSI of a flat series is 50, as the engine's", () => {
  const got = I.rsi(Array(30).fill(100), 14);
  assert.ok(!Number.isFinite(got[13]));
  assert.deepEqual(got.slice(14), Array(16).fill(50));
  assert.equal(I.rsi(Array.from({ length: 30 }, (_, i) => 100 + i), 14).at(-1), 100);
});

test("the 52-week high and low on daily candles are the previous 252 candles', the candle itself left out", () => {
  const bars = Array.from({ length: 260 }, (_, i) => ({ o: 0, c: 0, v: 0, h: 100 + (i % 7) + (i === 3 ? 50 : 0), l: 50 - (i % 5) - (i === 255 ? 9 : 0) }));
  const { high, low } = I.priorHighLow(bars, 252);
  assert.ok(!Number.isFinite(high[251]) && !Number.isFinite(low[251]));          // blank until 252 candles before it
  assert.equal(high[252], 153);                                                // candles 0..251: the spike at 3
  assert.equal(high[256], Math.max(...bars.slice(4, 256).map((b) => b.h)));     // the spike has left the window
  assert.equal(low[255], 46);                                                  // its own low (41) is left out
  assert.equal(low[256], 41);
});

test("daily candles are told from weekly and intraday ones by their spacing", () => {
  const day = 86_400_000;
  const weekdays = [0, 1, 2, 3, 4, 7, 8, 9, 10, 11].map((d) => d * day);
  assert.ok(I.dailySpacing(weekdays));
  assert.ok(!I.dailySpacing([0, 7, 14, 21].map((d) => d * day)));
  assert.ok(!I.dailySpacing([0, 1, 2, 3].map((m) => m * 300_000)));
});

test("the 52-week study uses the rule's window on daily candles and says what it draws", () => {
  const src = read("src/charts/price/studies.ts");
  assert.match(src, /!intraday && I\.dailySpacing\(times\) \? I\.priorHighLow\(bars, 252\) : I\.rangeHighLow\(bars, times, 365 \* 86_400_000\)/);
  assert.match(src, /On daily candles, the highest high and lowest low of the 252 candles before each one, the candle itself left out, as in the rules\./);
});
