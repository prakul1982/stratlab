// How an experiment page writes its numbers: falls, charges, forex prices and coin quantities. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { charge, fall, price, priceDp, qty } from "../src/lib/format.ts";

test("a fall has one decimal and never reads −0%", () => {
  assert.equal(fall(-2.46), "−2.5%");
  assert.equal(fall(2.46), "−2.5%");          // the shuffle check keeps falls as positive depths
  assert.equal(fall(-0.04), "0%");
  assert.equal(fall(0), "0%");
  assert.equal(fall(null), "–");
});

test("a charge under one unit keeps its cents, and nothing is −₹0", () => {
  assert.equal(charge(1238.4, "INR"), "−₹1,238");
  assert.equal(charge(0.006, "USD"), "−$0.01");        // the smallest line the backend lists (over half a cent)
  assert.equal(charge(0.42, "USD"), "−$0.42");
  assert.equal(charge(0, "INR"), "₹0");
});

test("spot forex is quoted to 5 decimals (yen pairs 3), others by size", () => {
  assert.equal(priceDp({ market: "FX", symbol: "EUR/USD" }), 5);
  assert.equal(priceDp({ market: "FX", symbol: "USD/JPY", currency: "JPY" }), 3);
  assert.equal(priceDp({ market: "IN", symbol: "RELIANCE" }), undefined);
  assert.equal(price(1.16321, "USD", priceDp({ market: "FX", symbol: "EUR/USD" })), "$1.16321");
  assert.equal(price(1421.16, "INR"), "₹1,421.16");
});

test("coin quantities line up to the instrument's step", () => {
  assert.equal(qty(0.0509138, 1e-8), "0.05091380");
  assert.equal(qty(0.05013551, 1e-8), "0.05013551");
  assert.equal(qty(85), "85");
  assert.equal(qty(1500, 1), "1,500");
});
