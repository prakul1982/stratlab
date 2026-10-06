// Indian rupee formatting: full, compact and chart-axis forms. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { axisInr, CRORE, inr, inrCompact, pctPlain, signed, signedInrCompact } from "../src/lib/format.ts";

test("inr groups the Indian way, whole rupees unless paise are asked for", () => {
  assert.equal(inr(100000), "₹1,00,000");
  assert.equal(inr(925), "₹925");
  assert.equal(inr(925.5, 2), "₹925.50");
  assert.equal(inr(-1849.32, 2), "−₹1,849.32");
  assert.equal(inr(-0.2), "₹0");
  assert.equal(inr(null), "–");
});

test("inrCompact uses lakh, crore and lakh crore", () => {
  assert.equal(inrCompact(925), "₹925");
  assert.equal(inrCompact(520000), "₹5.2 lakh");
  assert.equal(inrCompact(3472 * CRORE), "₹3,472 cr");
  assert.equal(inrCompact(925 * CRORE), "₹925 cr");
  assert.equal(inrCompact(1.51 * 1e5 * CRORE), "₹1.51 lakh cr");
  assert.equal(inrCompact(-18 * CRORE), "−₹18 cr");
  assert.equal(inrCompact(99999.8 * CRORE), "₹1 lakh cr");     // rounds up into the next unit, never "₹1,00,000 cr"
  assert.equal(inrCompact(undefined), "–");
});

test("signedInrCompact puts a plus on gains", () => {
  assert.equal(signedInrCompact(296 * CRORE), "+₹296 cr");
  assert.equal(signedInrCompact(-18 * CRORE), "−₹18 cr");
});

test("axisInr shortens axis ticks", () => {
  assert.equal(axisInr(1.45e5 * CRORE), "₹1.45L cr");
  assert.equal(axisInr(1.475e5 * CRORE), "₹1.475L cr");
  assert.equal(axisInr(1.5e5 * CRORE), "₹1.5L cr");
  assert.equal(axisInr(3472 * CRORE), "₹3,472 cr");
  assert.equal(axisInr(520000), "₹5.2L");
  assert.equal(axisInr(925), "₹925");
});

test("pctPlain and signed", () => {
  assert.equal(pctPlain(0.213, 2), "0.21%");
  assert.equal(signed(1234567), "+12,34,567");
  assert.equal(signed(-5), "−5");
  assert.equal(signed(0), "0");
});
