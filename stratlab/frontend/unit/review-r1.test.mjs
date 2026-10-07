// Fixes from the first fresh-eyes review (round 1): shared helpers the pages use. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { titleFor, withBrand, DEFAULT_TITLE } = await import("../src/lib/title.ts");
const { menuView } = await import("../src/lib/spaces.ts");

test("every page has its own tab title (R1-010)", () => {
  assert.equal(titleFor("/holdings"), "Holdings · StratLab");
  assert.equal(titleFor("/tax-report?fy=2025"), "Tax report · StratLab");
  assert.equal(titleFor("/research/IN/reliance"), "RELIANCE · StratLab");
  assert.equal(titleFor("/research/US/AAPL/deep"), "AAPL deep dive · StratLab");
  assert.equal(titleFor("/n/abc/e/2"), "Notebooks · StratLab");
  assert.equal(titleFor("/trade/g/practise"), "Practise · Trade · StratLab");
  assert.equal(titleFor("/admin/users"), "Admin · StratLab");
  assert.equal(titleFor("/settings"), "Settings · StratLab");
  assert.equal(titleFor("/nowhere"), DEFAULT_TITLE);
  assert.equal(withBrand("RELIANCE ₹1,408"), "RELIANCE ₹1,408 · StratLab");
  // no two menu pages share a title
  const seen = new Set();
  for (const p of ["/holdings", "/tax-report", "/money/net-worth", "/alerts", "/research/screens", "/trade/journal", "/paper", "/library"]) {
    assert.ok(!seen.has(titleFor(p)), p);
    seen.add(titleFor(p));
  }
});

test("the menu follows the address, not the last space used (R1-011)", () => {
  assert.equal(menuView("/n/abc/e/1", "money"), "trade");
  assert.equal(menuView("/holdings", "trade"), "money");
  assert.equal(menuView("/research/IN/TCS", "money"), "invest");
  assert.equal(menuView("/admin", "money"), "mine");              // its breadcrumb says Mine › Admin
  assert.equal(menuView("/settings", "trade"), "mine");
  assert.equal(menuView("/holdings", "mine", true), "mine");      // a page pinned to Mine keeps Mine's menu
  assert.equal(menuView("/holdings", "mine", false), "money");
  assert.equal(menuView("/", "invest"), "invest");               // the front door goes on to the space showing
});
