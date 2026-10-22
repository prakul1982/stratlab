// Round 75 (20 Oct 2026): the signed-out visitor — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a public page still loading fills the screen, so its footer doesn't jump when the page arrives (R75-002)", () => {
  assert.match(read("src/styles.css"), /main\.pub-main:has\(\.k-skel-box\) \{ min-height: 100vh; \}/);
});

test("plan limits are named as the plan cards name them, and the 404 page's FAQ card doesn't say 'Tips' (R75-003, R75-005)", () => {
  assert.match(read("src/content/legal.ts"), /Plan limits \(backtests, AI builds, strategies paper traded at a time\) apply per account\./);
  assert.doesNotMatch(read("src/content/legal.ts") + read("src/content/seo.ts"), /limits on experiments|\(experiments, AI builds/);
  assert.match(read("src/pages/Gate.tsx"), /title="Questions">Advice, real trades, options, invites and your data\./);
});
