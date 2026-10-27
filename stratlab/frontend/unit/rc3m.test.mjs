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

test("RC3M-005: the Rates page says when the tax rate is worked under another year's rules than the saved inputs' year", () => {
  const src = read("src/pages/money/RatesPage.tsx");
  assert.match(src, /rules_fy\?: number/);
  assert.match(src, /d\.mine\.rules_fy != null && d\.mine\.rules_fy !== d\.mine\.fy \? `, under the \$\{fyLabel\(d\.mine\.rules_fy\)\} rules`/);
});

test("RC3M-006: the tax report says when some company's bonuses and splits couldn't be read yet", () => {
  const src = read("src/pages/TaxReportPage.tsx");
  assert.match(src, /corp_left\?: number/);
  assert.match(src, /data-testid="tax-corp-left"/);
  assert.match(src, /bonuses and splits of \{rep\.corp_left\} \{rep\.corp_left === 1 \? "company" : "companies"\} couldn't be read yet/);
});

test("RC3M-006: Tax tools says how many held stocks' dividends are still being read", () => {
  const src = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(src, /checking\?: number/);
  assert.match(src, /data-testid="dividends-checking"/);
  assert.match(src, /Still reading the dividends of \{v\.checking\} stock/);
});
