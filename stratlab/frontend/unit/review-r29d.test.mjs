import { test } from "node:test";
import assert from "node:assert/strict";
import { legendIndex } from "../src/charts/price/legend.ts";
import { stageDaysText } from "../src/lib/stageDays.ts";

test("the legend reads the newest candle after Next candle adds one (R29D-003)", () => {
  assert.equal(legendIndex(-1, 10), 9);
  assert.equal(legendIndex(-1, 11), 10);      // a candle added: the header moves with it
  assert.equal(legendIndex(4, 10), 4);        // a pointer on a candle keeps it
  assert.equal(legendIndex(12, 10), 9);       // a stale index past the bars falls back to the newest
  assert.equal(legendIndex(-1, 0), -1);
});

test("a stage that began before the look-back reads as a lower bound (R29D-002)", () => {
  assert.equal(stageDaysText(116, true), "116+ days");
  assert.equal(stageDaysText(116, false), "116 days");
  assert.equal(stageDaysText(1, false), "1 day");
});
