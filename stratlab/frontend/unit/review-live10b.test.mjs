// LIVE10B (17 Nov 2026): the live end-to-end review of Release 60. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10B-024: a holdings file naming stocks already held is asked about, and the chosen way is said before reading", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /overlap_ok: overlapOk/);                                         // sent only once the user says so
  assert.match(page, /data-testid="holdings-overlap"/);
  assert.match(page, />Add these shares too</);
  assert.match(page, /setReplacing\(f\); \}\}>Start again with this file</);            // the replace path keeps its confirm
  assert.match(page, /data-testid="holdings-mode-note"/);
  assert.match(page, /you're asked before anything is added/);
});
