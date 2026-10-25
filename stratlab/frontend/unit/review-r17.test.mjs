// Round 17 (plans and payments, live): the visitor's Free card follows the billing switch, /plans opens with the prices'
// words, the Billed switch gets two columns, a count past the limit reads as the limit.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { countOf } = await import("../src/lib/account.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("R17-001: the visitor's period label is the switch's, Free included", () => {
  assert.match(read("src/pages/Login.tsx"), /const per = showYear && period === "year" \? "year" : "month";/);
});

test("R17-003: the Billed switch's field spans two columns", () => {
  assert.match(read("src/styles.css"), /\.k-seg\[aria-label="Billing period"\]\) \{ grid-column: span 2; \}/);
});

test("R17-004: a count past the limit reads as the limit", () => {
  assert.equal(countOf(8, 2), "2 of 2 (limit reached; 8 used)");        // R22-001 moved "limit reached" into brackets; R48-013 keeps the real count
  assert.equal(countOf(2, 2), "2 of 2 (limit reached)");
  assert.equal(countOf(1, 2), "1 of 2");
  assert.match(read("src/pages/NotebookPage.tsx"), /disabled=\{running \|\| outOfRuns \|\| \(!inst && !group\)\}/);     // DP1-012: nor before a market is chosen
});
