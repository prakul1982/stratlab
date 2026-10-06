// The period buttons on a daily history (Market breadth): which are offered, and that each one cuts the days differently.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { cutSeries, firstInPeriod, isPeriod, offeredPresets, periodDays, spanDays } from "../src/lib/period.ts";

const days = (n, end = "2026-10-05") => Array.from({ length: n }, (_, i) => new Date(Date.parse(end) - (n - 1 - i) * 86_400_000).toISOString().slice(0, 10));

test("a period is a preset, all, or a number with a unit", () => {
  for (const p of ["3m", "6m", "1y", "2y", "all", "45 days", "2 weeks", "18 months", "3 years"]) assert.ok(isPeriod(p), p);
  for (const p of ["", "5y", "0 days x", "1000 days", "ten days", null, 3]) assert.ok(!isPeriod(p), String(p));
});

test("periodDays counts calendar days, and all has none", () => {
  assert.equal(periodDays("3m"), 91);
  assert.equal(periodDays("1y"), 365);
  assert.equal(periodDays("45 days"), 45);
  assert.equal(periodDays("2 weeks"), 14);
  assert.equal(periodDays("all"), null);
});

test("only the presets shorter than the stored history are offered, then All", () => {
  assert.deepEqual(offeredPresets(40).map((o) => o.value), ["all"]);
  assert.deepEqual(offeredPresets(100).map((o) => o.value), ["3m", "all"]);
  assert.deepEqual(offeredPresets(400).map((o) => o.value), ["3m", "6m", "1y", "all"]);
  assert.deepEqual(offeredPresets(800).map((o) => o.value), ["3m", "6m", "1y", "2y", "all"]);
});

test("each period starts at a different day, counted back from the last one", () => {
  const d = days(800);
  assert.equal(spanDays(d), 799);
  const starts = ["3m", "6m", "1y", "2y", "all"].map((p) => firstInPeriod(d, p));
  assert.deepEqual(starts, [...starts].sort((a, b) => b - a));            // longer period, earlier start
  assert.equal(new Set(starts).size, 5);
  assert.equal(starts[4], 0);
  assert.equal(d.length - starts[0], 92);                                // 91 days back, both ends in
  assert.equal(d.length - firstInPeriod(d, "45 days"), 46);
});

test("a period longer than the history shows all of it", () => {
  const d = days(30);
  assert.equal(firstInPeriod(d, "1y"), 0);
  assert.equal(firstInPeriod(d, "5 years"), 0);
  assert.equal(firstInPeriod([], "3m"), 0);
});

test("cutSeries cuts every series at the same place and leaves the rest as it was", () => {
  const h = { days: days(5), adv: [1, 2, 3, 4, 5], trin: [null, 1, 2, 3, 4] };
  const cut = cutSeries(h, 2);
  assert.deepEqual(cut.adv, [3, 4, 5]);
  assert.deepEqual(cut.trin, [2, 3, 4]);
  assert.equal(cut.days.length, 3);
  assert.equal(cutSeries(h, 0), h);
});
