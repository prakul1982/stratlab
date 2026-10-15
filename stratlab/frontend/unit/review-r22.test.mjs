// Round 22 (plans and payments, live): Account's usage rows read like the pages, the deep dive's limit line is a sentence,
// both Plans pages word the rupee line alike, a visitor's /plans is the prices alone, Data and jobs says a job's error plainly.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

const { monthlyUse, aiBuildsUse, deepDiveLimitLine } = await import("../src/lib/account.ts");
const { chargedLine } = await import("../src/lib/currency.ts");
const { isPlansPath } = await import("../src/lib/deepLinks.ts");
const { plainError } = await import("../src/pages/admin/attention.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("R22-001: Account's usage rows never show a count past the limit", () => {
  assert.equal(monthlyUse(16, 10), "10 of 10 (limit reached)");
  assert.equal(monthlyUse(9, 2, 2, "early access", "Free"), "2 of 2 (limit reached)");
  assert.equal(monthlyUse(3, 10), "3 of 10");
  assert.equal(aiBuildsUse(15, 10), "10 of 10 (limit reached)");
  assert.match(read("src/lib/account.ts"), /if \(limit != null\) return countOf\(used, limit\);/);
});

test("R22-002: the deep dive's limit line is a sentence", () => {
  assert.equal(deepDiveLimitLine(2, 2, 1, 1),
    "Companies opened this month: 2 of 2 (limit reached). Decks: 1 of 1 (limit reached). Opening a company again this month doesn't count.");
  assert.equal(deepDiveLimitLine(10, 15, 7, 5),
    "Companies opened this month: 10 of 15. Decks: 5 of 5 (limit reached). Opening a company again this month doesn't count.");
  assert.equal(deepDiveLimitLine(1, 2, 0, null), "Companies opened this month: 1 of 2. Opening a company again this month doesn't count.");
  assert.match(read("src/pages/DeepDive.tsx"), /deepDiveLimitLine\(/);
});

test("R22-004: the signed-in card words the rupee line as the visitor's, and the lines come in the same order", () => {
  assert.equal(chargedLine("₹6,999", false, "year", "$73.57"), "Charged as ₹6,999 / year (about $73.57 today)");
  assert.equal(chargedLine("₹699", true, "month", null), "Charged as ₹699 / month incl. GST");
  const plans = read("src/pages/PlansPage.tsx");
  assert.ok(plans.indexOf("data-testid={`charged-${p}`}") < plans.indexOf("Saves {savingOf(p)} a year"), "Charged line before Saves line");
  const login = read("src/pages/Login.tsx");
  assert.ok(login.indexOf("Charged as") < login.indexOf("lp-save"), "the visitor's order");
});

test("R22-005: a visitor's /plans draws the prices alone, never the landing page scrolled down to them", () => {
  assert.equal(isPlansPath("/plans"), true);
  assert.equal(isPlansPath("/plans/"), true);
  assert.equal(isPlansPath("/plans?x=1"), true);
  assert.equal(isPlansPath("/pricing"), false);
  assert.equal(isPlansPath("/"), false);
  assert.match(read("src/visitor/VisitorApp.tsx"), /plansOnly=\{isPlansPath\(pathname\)\}/);
  assert.match(read("src/pages/Login.tsx"), /const section = plansOnly \? null : asked;/);
});

test("R22: Data and jobs says a job's network error plainly and keeps the raw text in a tooltip", () => {
  const raw = "NFO:FINNIFTY next: HTTPSConnectionPool(host='api.kite.trade', port=443): Read timed out. (read timeout=10)";
  const e = plainError(raw);
  assert.equal(e.text, "NFO:FINNIFTY next: Kite didn't answer in time");
  assert.equal(e.full, raw);
  const data = read("src/pages/admin/DataSection.tsx");
  assert.equal((data.match(/title=\{plainError\(/g) ?? []).length, 2);
  assert.doesNotMatch(data, /\{j\.error\}|\{job\.error\}/);
});
