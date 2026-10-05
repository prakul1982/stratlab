// The closing auction desk's helpers: the auction's steps from the day's timetable, and the gap and quantity text.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import * as C from "../src/lib/closingAuction.ts";

const TT = { since: "2026-08-03", open: "09:15", cas_stocks_continuous_end: "15:15", other_continuous_end: "15:30",
  auction: ["15:15", "15:35"], order_entry: ["15:20", "15:30"], derivatives_close: "15:40", settlement_fixed_by: "15:30", source: "" };

test("the auction's steps follow the timetable and mark the current one", () => {
  const s = C.steps(TT, "entry");
  assert.deepEqual(s.map((x) => [x.from, x.to]), [["09:15", "15:15"], ["15:15", "15:20"], ["15:20", "15:30"], ["15:30", "15:35"]]);
  assert.deepEqual(s.filter((x) => x.now).map((x) => x.id), ["entry"]);
  assert.deepEqual(C.steps({ ...TT, auction: null, order_entry: null }, "none"), []);
});

test("gaps keep their sign and two places", () => {
  assert.equal(C.gapText(0.4249), "+0.42%");
  assert.equal(C.gapText(-1.1), "−1.10%");
  assert.equal(C.gapText(0.001), "0.00%");
  assert.equal(C.gapText(null), "–");
});

test("quantities in lakh and crore", () => {
  assert.equal(C.qtyText(12345), "12,345");
  assert.equal(C.qtyText(123456), "1.2 lakh");
  assert.equal(C.qtyText(-25_000_000), "−2.5 crore");
  assert.equal(C.qtyText(undefined), "–");
});

test("the page re-reads only while the auction can still change", () => {
  assert.deepEqual(C.LIVE_PHASES, ["before", "transition", "entry", "matching"]);
});
