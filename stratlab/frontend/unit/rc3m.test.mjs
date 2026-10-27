// RC3M (27 Oct 2026): the Money and Invest review, the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC3M-003: Tax tools says the rate of the year it shows, with the note the year brings (7.5% in FY 2020-21)", () => {
  const src = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(src, /A company cuts \{\+\(y\.tds\.rate \* 100\)\.toFixed\(2\)\}% TDS/);
  assert.match(src, /y\.tds\.note \?/);
  assert.match(src, /note\?: string \| null/);
  assert.doesNotMatch(src, /A company cuts 10% TDS/);
});
