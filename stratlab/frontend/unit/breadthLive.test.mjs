// Market breadth while the market is open: the live card's title and series, and the business-updates helpers.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { liveSeries, liveTitle } from "../src/lib/breadthLive.ts";
import { bizChange, bizValue, periodName } from "../src/lib/biz.ts";

const FIELDS = ["adv", "dec", "unch", "a20", "n20", "a50", "n50", "a200", "n200", "idx"];

test("the live title says the time of the newest point", () => {
  assert.equal(liveTitle({ as_of: "10:45" }), "Today, live as of 10:45");
  assert.equal(liveTitle({ as_of: null }), "Today, live");
});

test("live points become one series per measure, shares worked out from the counts", () => {
  const s = liveSeries({ fields: FIELDS, points: [
    ["09:30", 230, 170, 12, 210, 400, 190, 400, 160, 380, 24000.5],
    ["09:45", 244, 161, 11, 216, 400, 195, 400, 0, 0, null],
  ] });
  assert.deepEqual(s.times, ["09:30", "09:45"]);
  assert.deepEqual(s.adv, [230, 244]);
  assert.deepEqual(s.dec, [170, 161]);
  assert.deepEqual(s.pct20, [52.5, 54]);
  assert.deepEqual(s.pct50, [47.5, 48.75]);
  assert.deepEqual(s.pct200, [42.11, null]);          // no stock with 200 days: no share, not 0%
  assert.deepEqual(s.idx, [24000.5, null]);
});

test("no points, no series", () => {
  const s = liveSeries({ fields: FIELDS, points: [] });
  assert.deepEqual(s.times, []);
  assert.deepEqual(s.pct50, []);
});

test("filed figures keep their unit and Indian grouping; changes are plain signed text", () => {
  assert.equal(bizValue(236013, "units"), "2,36,013 units");
  assert.equal(bizValue(33275, "₹ billion"), "₹33,275 billion");
  assert.equal(bizValue(34.2, "%"), "34.2%");
  assert.equal(bizValue(null, "units"), "–");
  assert.equal(bizChange(24.4, "units"), "+24.4%");
  assert.equal(bizChange(-3.04, "units"), "−3.0%");
  assert.equal(bizChange(1.234, "%"), "+1.23 pts");
  assert.equal(bizChange(null, "units"), "–");
  assert.equal(periodName("2026-09"), "Sep 2026");
  assert.equal(periodName("2026-09", "quarter"), "Q2 FY27");
});
