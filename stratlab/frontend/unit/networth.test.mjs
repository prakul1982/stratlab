// The net-worth headline change and the loan's expected-rate note. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { expectedNote, netWorthDelta } from "../src/lib/networth.ts";

const hist = [{ d: "2026-08-01", net: 100 }, { d: "2026-09-01", net: 120 }, { d: "2026-10-01", net: 40, partial: ["EPF"] }];

test("the change is the live total less the latest complete snapshot", () => {
  assert.deepEqual(netWorthDelta(130, null, hist), { change: 10, since: "2026-09-01" });
  assert.deepEqual(netWorthDelta(130, [], hist.slice(0, 1)), { change: 30, since: "2026-08-01" });
});

test("today's own snapshot (an entry changed today) is passed over", () => {
  const withToday = [...hist, { d: "2026-10-15", net: 130 }];
  assert.deepEqual(netWorthDelta(130, null, withToday, "2026-10-15"), { change: 10, since: "2026-09-01" });
});

test("no change is shown when the live total is partial or no snapshot is complete", () => {
  assert.equal(netWorthDelta(130, ["EPF"], hist), null);
  assert.equal(netWorthDelta(130, null, [hist[2]]), null);
  assert.equal(netWorthDelta(130, null, []), null);
});

test("the expected-rate note says so without a spread", () => {
  assert.equal(expectedNote("5.50%", 2.5), "repo 5.50% + 2.50");
  assert.equal(expectedNote("5.50%", null), "Not enough repo history to work this out");
  assert.equal(expectedNote("5.50%", undefined), "Not enough repo history to work this out");
});
