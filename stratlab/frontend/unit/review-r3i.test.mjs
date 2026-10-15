// Review 3i (frontend): the compare page names every change (direction both ways, most in one trade, product, short
// exit) and counts checks as other pages do; the chart's RSI of a flat series is 50 as the engine's; its 52-week line on
// daily candles is the rule's own (the previous 252 candles, the candle itself left out).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as I from "../src/charts/price/indicators.ts";

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("the compare page writes a direction of both ways as itself, not long", () => {
  const src = read("src/pages/CompareExperiments.tsx");
  assert.match(src, /const SIDE: Record<string, string> = \{ long: "long only", short: "short only", both: "both ways" \};/);
  assert.match(src, /`Direction: \$\{SIDE\[sa\.side \?\? "long"\]\} → \$\{SIDE\[sb\.side \?\? "long"\]\}`/);
  assert.doesNotMatch(src, /sa\.side === "short" \? "short" : "long"/);
});

test("the compare page lists most in one trade, the product and the short exit among the changes", () => {
  const src = read("src/pages/CompareExperiments.tsx");
  assert.match(src, /\["maxAlloc", "Most in one trade", "%"\]/);
  assert.match(src, /`Product: \$\{sa\.product \?\? "auto"\} → \$\{sb\.product \?\? "auto"\}`/);
  assert.match(src, /rules\(sa, "shortExit" as "exit"\) !== rules\(sb, "shortExit" as "exit"\)\) out\.push\(`Short exit: /);
});

test("the compare page counts the checks with checksLine, out of four like the other pages", () => {
  const src = read("src/pages/CompareExperiments.tsx");
  assert.match(src, /\["Checks passed", \(e\) => checksLine\(e\.verdict\.passed, e\.verdict\.total\)/);
  assert.match(src, /import \{ checksLine \} from "\.\.\/lib\/tradeUi";/);
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
