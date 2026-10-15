// Review 11B: the closing auction page labels an earlier day's read as that day's close, not as the live value.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../src/pages/trade/ClosingAuctionPage.tsx", import.meta.url), "utf8");

test("the indices' and stocks' headers say Close / Final price for a read that isn't from today", () => {
  assert.match(page, /const done = v\.phase === "closed" \|\| !!v\.from_stored \|\| !v\.fresh;/);
  assert.match(page, /const final = v\.phase === "closed" \|\| !!v\.from_stored \|\| !v\.fresh \|\|/);
});
