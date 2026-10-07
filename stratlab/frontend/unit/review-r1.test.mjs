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

test("a signed-out deep link names its page and offers the public company page (R1-013)", async () => {
  const { gateFor } = await import("../src/lib/gate.ts");
  assert.equal(gateFor("/", "https://x.test"), null);
  assert.deepEqual(gateFor("/tax-report", "https://x.test"), { name: "Tax report", publicUrl: null });
  assert.deepEqual(gateFor("/research/IN/reliance", "https://x.test/"), { name: "RELIANCE", publicUrl: "https://x.test/stocks/in/RELIANCE" });
  assert.equal(gateFor("/research/US/AAPL/deep", "http://127.0.0.1:8765").publicUrl, "http://127.0.0.1:8765/stocks/us/AAPL");
  assert.equal(gateFor("/somewhere-else", "https://x.test").name, "this page");
});

test("the Money pages open on one financial year (R1-006)", async () => {
  const { pickFy, fyLabel } = await import("../src/lib/fy.ts");
  const years = [2026, 2025, 2024];
  assert.equal(pickFy(years, 2026, () => true, null), 2025);                    // the year being filed now
  assert.equal(pickFy(years, 2026, (y) => y === 2024, null), 2024);             // ...unless it's empty: the latest with data
  assert.equal(pickFy(years, 2026, () => false, null), 2026);                   // nothing anywhere: this year
  assert.equal(pickFy(years, 2026, () => true, 2024), 2024);                    // a year picked by hand wins
  assert.equal(pickFy(years, 2026, () => true, 2019), 2025);                    // ...when the page has it
  assert.equal(fyLabel(2025), "FY 2025-26");
});

test("checks are counted out of four everywhere (R1-020)", async () => {
  const { checksLine } = await import("../src/lib/tradeUi.ts");
  assert.equal(checksLine(2, 4), "2 of 4 checks passed");
  assert.equal(checksLine(3, 3), "3 of 4 checks passed · 1 not run");
});

test("a date is typed and read day first (R1-016)", async () => {
  const { parseDay, showDay } = await import("../src/lib/dateInput.ts");
  assert.equal(parseDay("9/2/2025"), "2025-02-09");          // 9 February, never 2 September
  assert.equal(parseDay("09-02-25"), "2025-02-09");
  assert.equal(parseDay("14 Aug 2025"), "2025-08-14");
  assert.equal(parseDay("14 august, 2025"), "2025-08-14");
  assert.equal(parseDay("14aug2025"), "2025-08-14");
  assert.equal(parseDay("2025-08-14"), "2025-08-14");          // what a browser's own calendar gives
  assert.equal(parseDay("31/02/2025"), null);                 // not a real day
  assert.equal(parseDay("14 Agu 2025"), null);
  assert.equal(parseDay("14 augx 2025"), null);
  assert.equal(parseDay(""), null);
  assert.equal(showDay("2025-02-09"), "9 Feb 2025");
  assert.equal(showDay(""), "");
});

test("a typed number is checked against its named limits, and the server's own checks read back (R1-050)", async () => {
  const { numberProblem, serverProblems, limitText } = await import("../src/lib/validate.ts");
  assert.equal(numberProblem("-5", { min: 0, above: true }), "Enter more than 0.");
  assert.equal(numberProblem("99999999999", { min: 0, above: true, max: 1e9 }), "Enter at most 1,00,00,00,000.");
  assert.equal(numberProblem("1,00,000", { min: 0, max: 1e12, unit: "₹" }), null);
  assert.equal(numberProblem("1e20", { min: 0, max: 1e12, unit: "₹" }), "Enter at most ₹10,00,00,00,00,000.");
  assert.equal(numberProblem("45", { min: 1, max: 28, whole: true }), "Enter at most 28.");
  assert.equal(numberProblem("2.5", { whole: true }), "Enter a whole number.");
  assert.equal(numberProblem("abc"), "Enter a number, like 10.");
  assert.equal(numberProblem("", { optional: true }), null);
  assert.equal(numberProblem(""), "Fill this in.");
  assert.equal(limitText(60, "%"), "60%");
  const f = serverProblems([
    { loc: ["body", "items", 0, "qty"], type: "less_than_equal", ctx: { le: 1e9 } },
    { loc: ["body", "value"], type: "greater_than_equal", ctx: { ge: 0 } },
    { loc: ["body", "name"], type: "string_too_long", ctx: { max_length: 60 } },
  ]);
  assert.deepEqual(f, { qty: "Enter at most 1,00,00,00,000.", value: "Enter 0 or more.", name: "Use at most 60 characters." });
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
