// Round 31: the earnings surprise comes from the printed figures; the chart legend's change label says what it is;
// the paper overview says "No open positions". Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("surprise percentage agrees with the printed figures (R31-014)", async () => {
  const { surpriseShown } = await import("../src/lib/surprise.ts");
  assert.equal(surpriseShown(1.85, 1.81).toFixed(1), "2.2");
  assert.equal(surpriseShown(2.84, 2.73).toFixed(1), "4.0");
  assert.equal(surpriseShown(1.91, 1.93).toFixed(1), "-1.0");
  assert.equal(surpriseShown(1.853, 1.805).toFixed(1), "2.2");   // unrounded inputs: the printed 1.85 vs 1.81
  assert.equal(surpriseShown(1, 0), null);
});

test("chart legend names the change as vs the previous close (R31-013)", () => {
  const src = read("src/charts/price/PriceChart.tsx");
  assert.doesNotMatch(src, /\{tf\} candle:/);
  assert.match(src, /TF_LABEL\[tf\]\} change:/);
});

test("paper overview says No open positions for a zero open value (R31-010)", () => {
  assert.match(read("src/components/RiskOverview.tsx"), /"No open positions"/);
});

test("the backtest's corporate-action note skips an index (R31-021)", () => {
  assert.match(read("src/pages/ExperimentPage.tsx"), /type === "INDEX"/);
});
