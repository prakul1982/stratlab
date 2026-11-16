// LIVE9B (16 Nov 2026 live review, reviewer B): the frontend side of lane fix9b.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE9B-001: a company page's wait holds the header's final shape (name, the exchange line, both date chips)", () => {
  const src = read("src/pages/Research.tsx");
  const wait = src.slice(src.indexOf("if (!c) return ("), src.indexOf("const ccy = c.currency"));
  assert.match(wait, /title=\{knownName\(region, sym\) \?\? sym\}/);          // the name this device last saw, not the bare symbol
  assert.match(wait, /lede=\{<span className="k-meta-wait">/);                // the "NSE · TCS" line's place
  assert.equal((wait.match(/className="k-meta-wait" aria-hidden="true"><Badge>/g) || []).length, 2);   // both chips' places
  assert.match(wait, /onRetry=\{\(\) => setTries\(\(n\) => n \+ 1\)\} page \/>/);   // the footer waits below the fold
});

test("LIVE9B-003: a whole-number percentage row or column is written whole, never with a fake '.0'", async () => {
  const { cellText, wholeOnly } = await import("../src/lib/companyTables.ts");
  assert.equal(wholeOnly([25, 26, null, 24]), true);
  assert.equal(wholeOnly([4.6, 7, null]), false);
  assert.equal(cellText(25, "pct", "IN", true), "25%");
  assert.equal(cellText(4.6, "pct", "IN"), "4.6%");
  assert.match(read("src/components/CompanyStatements.tsx"), /cellText\(r\.values\[i\], r\.kind, region, r\.kind === "pct" && wholeOnly\(r\.values\)\)/);
  assert.match(read("src/components/CompanyPeers.tsx"), /pctCell\(r\.ebitda, "ebitda"\)/);
});

test("LIVE9B-007: business updates in one unit per kind, old figures aged, filing years, no tag on every row", async () => {
  const { bizValueOne, monthsBefore } = await import("../src/lib/biz.ts");
  assert.equal(bizValueOne(45520, "₹ million"), "₹4,552 crore");
  assert.equal(bizValueOne(3085, "₹ mn"), "₹309 crore");
  assert.equal(bizValueOne(6.51, "₹ lakh crore"), "₹6,51,000 crore");
  assert.equal(bizValueOne(5542, "₹ crore"), "₹5,542 crore");
  assert.equal(bizValueOne(104.3, "Lac MT"), "104.3 lakh tonnes");
  assert.equal(bizValueOne(19.9, "Mn T"), "19.9 million tonnes");
  assert.equal(bizValueOne(3519, "units"), "3,519 units");
  assert.equal(monthsBefore("2025-03", new Date(2026, 10, 17)), 20);
  const page = read("src/pages/BizUpdatesPage.tsx");
  assert.match(page, /months old/);
  assert.match(page, /new Set\(mine\.rows\.map\(\(r\) => r\.kind\)\)\.size > 1 \?/);       // the From column only when holdings and watchlist mix
  assert.doesNotMatch(page, /<Badge tone="plain" dot=\{false\}>\{kindName/);
  assert.match(read("src/components/BizUpdates.tsx"), /thisYear \? \{ year: false \} : \{\}/);
});

test("LIVE9B-008: the money calendar links the filing instead of writing its address, and tags rows only when kinds mix", () => {
  const src = read("src/pages/money/MoneyCalendarPage.tsx");
  assert.match(src, /<a className="link" href=\{safeHref\(e\.link\)\} target="_blank" rel="noopener noreferrer">Filing ↗<\/a>/);
  assert.match(src, /const tag = new Set\(events\.map\(\(e\) => e\.cat\)\)\.size > 1;/);
  assert.match(src, /\{tag && <span className=\{`badge mc-cat/);
  assert.match(read("src/styles.css"), /\.mc-ev\.untagged \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});
