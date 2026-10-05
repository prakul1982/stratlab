// Strike rules in words (the builder's summary and the session's rules strip) and the India VIX panel's words.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { legRule, PICKS } from "../src/lib/options.ts";
import { vixChange, vixNum, vixPercentileLine } from "../src/lib/vix.ts";

const leg = (p) => ({ side: "sell", opt: "PE", offset: 0, lots: 1, ...p });

test("a leg's strike rule in a few words", () => {
  assert.equal(legRule(leg({}), "strikes"), "ATM");
  assert.equal(legRule(leg({ offset: 3 }), "strikes"), "3 OTM");
  assert.equal(legRule(leg({ offset: -200 }), "points"), "200 pts ITM");
  assert.equal(legRule(leg({ pick: "delta", delta: 0.2 }), "strikes"), "Δ 0.20");
  assert.equal(legRule(leg({ pick: "delta_range", delta: 0.15, deltaTo: 0.25 }), "strikes"), "Δ 0.15–0.25");
  assert.equal(legRule(leg({ pick: "premium", premium: 40, premiumOp: "gte" }), "strikes"), "≥ ₹40");
  assert.equal(legRule(leg({ pick: "premium" }), "strikes"), "≈ ₹50");
  assert.equal(legRule(leg({ pick: "straddle_pct", pct: 30 }), "strikes"), "30% of straddle");
  assert.deepEqual(PICKS.map(([v]) => v), ["offset", "delta", "delta_range", "premium", "straddle_pct"]);
});

test("India VIX words stay numbers, never verdicts", () => {
  const q = { value: 15.03, prev_close: 14.46, change: 0.57, change_pct: 3.94 };
  assert.equal(vixChange(q), "+0.57 (+3.94%)");
  assert.equal(vixChange({ ...q, change: -1.2, change_pct: -7.5 }), "−1.20 (−7.50%)");
  assert.equal(vixChange({ ...q, change: null }), null);
  assert.equal(vixNum(null), "–");
  assert.equal(vixPercentileLine({ days: 250, need: 60, percentile: 62.4 }), "Higher than 62% of the past year's closes");
  assert.equal(vixPercentileLine({ days: 12, need: 60, percentile: null }), "12 days stored; the comparison starts at 60");
});
