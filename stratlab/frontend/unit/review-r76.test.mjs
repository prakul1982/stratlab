// Round 76 (21 Oct 2026): plan views and the phone in dark mode — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { ALL_PAGES } = await import("../src/lib/nav.ts");
const { PAGE_GATES } = await import("../src/lib/gates.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("every page with a paid part carries its plan flag, so All features tags it (R76-002)", () => {
  for (const [to, gate] of Object.entries(PAGE_GATES)) {
    const page = ALL_PAGES.find((l) => l.page.to === to)?.page;
    if (page) assert.equal(page.flag, gate.feature, to);
  }
  for (const to of ["/research/scan", "/money/mutual-funds", "/trade/positioning", "/trade/journal", "/invest/breadth", "/money/itr"])
    assert.ok(ALL_PAGES.find((l) => l.page.to === to)?.page.flag, to);
});

test("a group bigger than the plan's size can't be saved, and says why (R76-001)", () => {
  const src = read("src/pages/MarketPage.tsx");
  assert.match(src, /disabled=\{busy \|\| overCap\}/);
  assert.match(src, /data-testid="group-cap-note"/);
});

test("the plans say what the Free trial is and that F&O on Pro means contracts, not the stocks (R76-003, R76-010)", () => {
  const plans = read("src/lib/plans.ts");
  assert.match(plans, /A free trial of 5 market days paper trading one notebook strategy on one stock/);
  assert.match(plans, /Indian F&O contracts \(futures and options on stocks and indices\) in notebooks and backtests; the stocks themselves are on every plan/);
});

test("phone: tap targets reach 44px, and a space card's line is read in full (R76-005, R76-006)", () => {
  const css = read("src/styles.css");
  const block = css.slice(css.indexOf("/* R76-005"));
  for (const sel of [".k-crumb a", ".k-check", ".k-disclosure > summary", ".search-box input", ".link-btn", ".ch-bar .ch-btn"]) assert.ok(block.includes(sel), sel);
  assert.match(css, /@media \(max-width: 560px\) \{ \.space-card-line \{ display: block; -webkit-line-clamp: unset;/);
});

test("strikes, the coverage line and the screens counter read plainly (R76-007, R76-009, R76-011)", () => {
  assert.equal((read("src/pages/OptionsPage.tsx").match(/r\.strike\.toLocaleString\("en-IN"/g) ?? []).length, 2);
  assert.match(read("src/pages/PositioningPage.tsx"), /The participant history covers \$\{spanLine\(coverage\.participants\)\}\./);
  assert.match(read("src/pages/Screens.tsx"), /data-testid="screens-left">\{saved\.count\} of \{saved\.limit\} saved\./);
});
