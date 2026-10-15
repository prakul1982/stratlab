// R10C: signs and units on the research pages, the deep dive and the screens. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { metricText, screenCap, screenNum, usdAmount } = await import("../src/lib/researchFormat.ts");

test("a negative per-share amount has its sign in front of the currency, as a true minus", () => {
  assert.equal(metricText({ label: "EPS TTM", value: -1.2, unit: "money" }, "USD"), "−$1.2");
  assert.equal(metricText({ label: "Book value", value: -45.3, unit: "money" }, "INR"), "−₹45.3");
  assert.equal(metricText({ label: "EPS TTM", value: -0.001, unit: "money" }, "USD"), "$0");         // never "$-0"
  assert.equal(metricText({ label: "EPS TTM", value: 1234.5, unit: "money" }, "INR"), "₹1,234.5");
});

test("a deep dive amount puts the sign first", () => {
  assert.equal(usdAmount(-1500), "−$1.50 billion");
  assert.equal(usdAmount(-12.25), "−$12.25 million");
  assert.equal(usdAmount(-0.001), "$0 million");
  assert.equal(usdAmount(215900), "$215.9 billion");
  assert.equal(usdAmount(950, "CAD"), "CAD 950 million");
  assert.equal(usdAmount(null), "–");
});

test("a US micro cap reads in millions, never $0.0 bn", () => {
  assert.equal(screenCap(12, "US"), "$12 mn");
  assert.equal(screenCap(950.4, "US"), "$950 mn");
  assert.equal(screenCap(4.25, "US"), "$4.3 mn");
  assert.equal(screenCap(85800, "US"), "$85.8 bn");
  assert.equal(screenCap(1000, "US"), "$1.0 bn");
  assert.equal(screenCap(735120, "IN"), "₹7,35,120 cr");
  assert.equal(screenCap(null, "US"), "–");
});

test("a screen figure that rounds to zero is never -0.0", () => {
  assert.equal(screenNum(-0.04, 1, "%"), "0.0%");
  assert.equal(screenNum(-0.004, 2), "0.00");
  assert.equal(screenNum(-3.26, 1, "%"), "−3.3%");
  assert.equal(screenNum(12.34, 1, "%"), "12.3%");
  assert.equal(screenNum(null), "–");
});
