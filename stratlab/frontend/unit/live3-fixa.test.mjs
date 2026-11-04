// LIVE3 review (live, 4 Nov), the FIXA lane's frontend checks.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const T = await import("../src/charts/price/ticks.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// a candle's `w` is its wall-clock time on the exchange's clock, kept as if it were UTC
const wall = (iso) => Date.parse(iso + "Z");

test("LIVE3-011: the chart says Live only while the market is open or a candle is forming now; shut, it says when it last closed", () => {
  const live = { live: true };
  const last15 = { t: wall("2026-11-04T09:45:00"), w: wall("2026-11-04T15:15:00") };
  // every combination: the market shut never says Live, whatever the source says
  for (const f of [{ live: true }, { delayed: true }, { live: true, delayed: true }])
    for (const streaming of [true, false]) for (const forming of [true, false])
      assert.notEqual(T.marketPill(false, f, streaming, forming, last15, "15m", "IN")?.cls, "live");
  assert.equal(T.marketPill(false, live, false, false, last15, "15m", "IN").text, "Closed · last close 4 Nov, 15:30 IST");
  assert.equal(T.marketPill(false, live, false, false, { t: 0, w: wall("2026-11-04T15:15:00") }, "1h", "IN").text, "Closed · last close 4 Nov, 15:30 IST");   // never past the session's close
  assert.equal(T.marketPill(false, live, false, false, { t: 0, w: wall("2026-11-04T00:00:00") }, "1d", "IN").text, "Closed · last close 4 Nov");
  assert.equal(T.marketPill(false, live, false, false, { t: 0, w: wall("2026-11-04T15:59:00") }, "1m", "US").text, "Closed · last close 4 Nov, 16:00 ET");
  assert.equal(T.marketPill(true, live, true, true, last15, "15m", "IN").text, "Live");
  // not told whether the market is open: Live only while the newest candle's window holds now (fresh prices)
  assert.equal(T.marketPill(null, live, false, true, last15, "15m", "IN").text, "Live");
  assert.equal(T.marketPill(undefined, live, false, false, last15, "15m", "IN"), null);
  assert.equal(T.marketPill(true, { delayed: true }, false, false, last15, "15m", "IN").text, "Delayed");
  assert.equal(T.marketPill(true, {}, false, false, last15, "15m", "IN"), null);
});

test("LIVE3-011: every chart with live prices is told its market (the company page's and the workspace's)", () => {
  const research = read("src/components/Research.tsx");
  assert.match(research, /marketOpen=\{open\} market=\{region\}/);
  assert.match(research, /marketState\(market\)\.open/);
  assert.match(read("src/components/watch/ChartWorkspace.tsx"), /marketOpen=\{open\} market=\{item\.market\}/);
  assert.doesNotMatch(read("src/charts/price/PriceChart.tsx"), /text: "Market closed"/);
});
