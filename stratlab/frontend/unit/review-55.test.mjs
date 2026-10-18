// Round 55: months written "Sep", never the browser's British "Sept"; long sector names break with a hyphen.
import { test } from "node:test";
import assert from "node:assert/strict";
import { monthLong, monthYear, softHyphens } from "../src/lib/format.ts";

test("months are Sep, not Sept (R55-011)", () => {
  assert.equal(monthLong("2025-09"), "Sep 2025");
  assert.equal(monthLong("2026-06-30"), "Jun 2026");
  assert.equal(monthYear("2026-09-15"), "Sep 26");
  assert.equal(monthLong("FY26"), "FY26");
});

test("a long word gets soft hyphens at syllable-like points (R55-001)", () => {
  assert.equal(softHyphens("Telecommunication").replace(/­/g, "-"), "Tele-com-mu-ni-ca-tion");
  assert.equal(softHyphens("Consumer Durables"), "Consumer Durables");
  assert.equal(softHyphens("Telecommunication").replace(/­/g, ""), "Telecommunication");
});
