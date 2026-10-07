// Short money moves to the next unit when a figure rounds up to it: ₹99,999 is ₹1.00L (not ₹100.0k), ₹99,99,999 is ₹1.0Cr
// (not ₹100.00L), $999,999 is $1.0M (not $1000.0k). A change that rounds to nothing has no sign. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { moneyShort, pct, bigMoney } = await import("../src/lib/format.ts");
const { compact, moneyCompact } = await import("../src/lib/chartFormat.ts");

test("a figure that rounds up to the next unit is written in it", () => {
  assert.equal(moneyShort(99999, "INR"), "₹1.00L");
  assert.equal(moneyShort(9999999, "INR"), "₹1.0Cr");
  assert.equal(moneyShort(999999, "USD"), "$1.0M");
  assert.equal(moneyShort(999_999_999, "USD"), "$1.0B");
  assert.equal(compact(99999, true), "1L");
  assert.equal(compact(9999999, true), "1Cr");
  assert.equal(compact(999999, false), "1M");
  assert.equal(moneyCompact(-99999, "INR"), "−₹1L");
});

test("figures that do not round up keep their unit", () => {
  assert.equal(moneyShort(99940, "INR"), "₹99.9k");
  assert.equal(moneyShort(100000, "INR"), "₹1.00L");
  assert.equal(moneyShort(12_345_678, "INR"), "₹1.2Cr");
  assert.equal(moneyShort(950, "INR"), "₹950");
  assert.equal(moneyShort(5, "USD"), "$5.00");
  assert.equal(compact(123456789, true), "12.3Cr");
  assert.equal(compact(12500, false), "12.5k");
  assert.equal(compact(0.5, true), "0.5");
});

test("a company's size rounds up to the next unit too, and a negative keeps its sign in front", () => {
  assert.equal(bigMoney(999_960_000_000, "USD"), "$1.00T");
  assert.equal(bigMoney(999_600_000, "USD"), "$1.0B");
  assert.equal(bigMoney(4_310_000_000_000, "USD"), "$4.31T");
  assert.equal(bigMoney(12_400_000_000, "USD"), "$12.4B");
  assert.equal(bigMoney(85_000_000, "USD"), "$85M");
  assert.equal(bigMoney(-1_500_000_000, "USD"), "-$1.5B");
  assert.equal(bigMoney(950_000, "USD"), "$950,000");
});

test("a change that rounds to nothing shows no sign", () => {
  assert.equal(pct(-0.04), "0.0%");
  assert.equal(pct(0.0004), "0.0%");
  assert.equal(pct(-0.04, 0), "0%");
  assert.equal(pct(-0.06), "−0.1%");
  assert.equal(pct(1.25), "+1.3%");
  assert.equal(pct(0), "0.0%");
});
