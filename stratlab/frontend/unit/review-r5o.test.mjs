// Round 5, the owner's review (R5O-…): the frontend side of the fixes.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a failed /me shows Retry, never a spinner that waits forever (R5O-002)", () => {
  const main = read("src/main.tsx");
  assert.match(main, /StratLab couldn't load your account: \{meError\}<\/span><AccountRetry \/>/);
  assert.doesNotMatch(main, /if \(!me\) return <Loading label="Checking access" \/>/);
  assert.match(main, /<AccountWait label="Checking access" \/>/);
  const wait = read("src/components/AccountWait.tsx");
  assert.match(wait, /if \(!meError\) return <Skeleton/);
  assert.match(wait, /label: busy \? "Trying again…" : "Retry"/);
  for (const p of ["src/pages/AdminPage.tsx", "src/pages/AccountPage.tsx", "src/pages/SettingsPage.tsx"])
    assert.match(read(p), /<AccountWait label=/, p);
  // one quiet second try on a 502/503/504 or no answer before the error shows
  assert.match(read("src/lib/app.tsx"), /e\.status !== 503 && e\.status !== 502 && e\.status !== 504\) throw e;/);
});

test("the theme map says a company without a checked ticker isn't listed, not 'private' (R5O-008)", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /\{co\.name\} \(not listed\)/);
  assert.doesNotMatch(r, /\(private\)/);
});
