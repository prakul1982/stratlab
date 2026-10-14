// Display fixes: signs on money, month labels, quantities, plan prices. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { bigMoney, money, moneyShort, monthYear, qty } from "../src/lib/format.ts";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("bigMoney puts a real minus before the symbol", () => {
  assert.equal(bigMoney(-5000, "USD"), "−$5,000");
  assert.equal(bigMoney(-2e9, "USD"), "−$2.0B");
  assert.equal(bigMoney(5000, "USD"), "$5,000");
  assert.equal(bigMoney(-0.2, "USD"), "$0");
});

test("money and moneyShort never show a signed zero or NaN", () => {
  assert.equal(money(-0.4, "INR"), "₹0");
  assert.equal(money(-1234, "INR"), "−₹1,234");
  assert.equal(moneyShort(NaN, "INR"), "–");
  assert.equal(moneyShort(undefined, "USD"), "–");
  assert.equal(moneyShort(-0.001, "USD"), "$0.00");
  assert.equal(moneyShort(-1500, "USD"), "−$1.5k");
});

test("qty guards non-finite values and groups by market", () => {
  assert.equal(qty(NaN), "–");
  assert.equal(qty(-0), "0");
  assert.equal(qty(208772), "2,08,772");
  assert.equal(qty(208772, undefined, "IN"), "2,08,772");
  assert.equal(qty(208772, undefined, "US"), "208,772");
  assert.equal(qty(0.05013551, 0.00000001, "US"), "0.05013551");
});

test("monthYear keeps a calendar day in its month whatever the zone", () => {
  assert.equal(monthYear("2026-03-01"), "Mar 26");
  assert.equal(monthYear("2025-03-01"), "Mar 25");
  assert.equal(monthYear(""), "–");
});

test("plan prices keep two decimals when fractional", async () => {
  const { money: planMoney } = await import("../src/lib/currency.ts");
  const row = { symbol: "$" };
  assert.equal(planMoney(row, 7.5, "USD"), "$7.50");
  assert.equal(planMoney(row, 8, "USD"), "$8");
});
