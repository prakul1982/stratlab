// The MONEY lane (Instinct deep QA, 1–2 Nov): imports, holdings, first clicks and small money fixes — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("MONEY-2: a holdings file adds by default, and Start again asks first, naming the count it replaces", () => {
  const p = read("src/pages/HoldingsPage.tsx");
  assert.match(p, /useState<"replace" \| "add">\("add"\)/);
  assert.match(p, /if \(how === "replace" && rows\.some\(\(r\) => !isUS\(r\)\)\) \{ setReplacing\(f\)/);
  assert.match(p, /title="Start again with this file\?" confirmLabel="Replace my holdings"/);
  assert.match(p, /This replaces your \{held\}/);
});

test("MONEY-6a: the holdings upload names what it saved, shows the accepted columns on a refusal, and never says failure over a save", () => {
  const p = read("src/pages/HoldingsPage.tsx");
  assert.match(p, /label="Stocks saved from this file"/);
  assert.match(p, /data-testid="holdings-format">A file of your own needs the columns <b>Symbol<\/b> \(or ISIN\), <b>Quantity<\/b> and <b>Average price<\/b>/);
  assert.match(p, /couldn't be opened here, so nothing was sent and your holdings are unchanged/);
  assert.match(p, /if \(!refused\(e\)\) \{ fail\(e\); load\(\); \}/);
});
