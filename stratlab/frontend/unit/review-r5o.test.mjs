// Round 5, the owner's review on the live site (8 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { quoteAt } from "../src/lib/format.ts";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const IST = "Asia/Kolkata";

test("each watchlist price carries the time it was traded, in the market's zone (R5O-003)", () => {
  const now = new Date("2026-10-08T09:31:00Z");                      // 15:01 IST
  assert.equal(quoteAt("2026-10-08T15:01:12+05:30", IST, now), "15:01 IST");
  assert.equal(quoteAt("2026-10-07T15:29:59+05:30", IST, now), "7 Oct, 15:29 IST");   // a stale quote reads as stale
  assert.equal(quoteAt("2026-10-08", IST, now), "8 Oct");              // a daily candle: its day only
  assert.equal(quoteAt(null, IST, now), "");
  // both tabs show it, from the same quotes
  assert.match(read("src/pages/Research.tsx"), /quoteAt\(q\.at, marketTz\(region\)\)/);
  assert.match(read("src/pages/InvestorHome.tsx"), /quoteAt\(r\.price_at, marketTz\(region\)\)/);
});
