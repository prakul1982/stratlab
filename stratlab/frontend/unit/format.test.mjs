// Indian rupee formatting: full, compact and chart-axis forms. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { axisInr, axisInrFor, CRORE, fmtDate, fmtDateTime, asOf, inr, inrCompact, pctPlain, signed, signedInrCompact } from "../src/lib/format.ts";

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

test("axisInrFor keeps every tick of one axis in one unit", () => {
  const lakh = axisInrFor(-160000);                 // an options payoff that reaches −₹1.6 lakh
  assert.deepEqual([50000, 0, -50000, -100000, -150000].map(lakh), ["₹0.5L", "₹0", "−₹0.5L", "−₹1L", "−₹1.5L"]);
  const rupees = axisInrFor(60000);
  assert.deepEqual([5000, 0, -50000].map(rupees), ["₹5,000", "₹0", "−₹50,000"]);
  assert.equal(axisInrFor(3 * CRORE)(2 * CRORE), "₹2 cr");
});

test("pctPlain and signed", () => {
  assert.equal(pctPlain(0.213, 2), "0.21%");
  assert.equal(signed(1234567), "+12,34,567");
  assert.equal(signed(-5), "−5");
  assert.equal(signed(0), "0");
});

test("fmtDate is day first: 6 Oct and 6 Oct 2026, never Oct 6", () => {
  assert.equal(fmtDate("2026-10-06"), "6 Oct 2026");
  assert.equal(fmtDate("2026-10-06", { year: false }), "6 Oct");
  assert.equal(fmtDate("2026-10-06T00:00:00"), "6 Oct 2026");
  assert.equal(fmtDate("2026-09-03"), "3 Sep 2026");                     // never "3 Sept"
  assert.match(fmtDate("2026-10-06", { weekday: true }), /^Tue,? 6 Oct 2026$/);
  assert.match(fmtDate("2026-10-06", { weekday: true, year: false }), /^Tue,? 6 Oct$/);
  assert.equal(fmtDate(new Date(2026, 9, 6, 23, 30)), "6 Oct 2026");
  assert.equal(fmtDate("2026-10-06T20:00:00Z", { tz: "Asia/Kolkata" }), "7 Oct 2026");   // a moment is read in its zone
  assert.equal(fmtDate(null), "–");
  assert.equal(fmtDate("not a date"), "–");
  assert.doesNotMatch(fmtDate("2026-10-06"), /^[A-Z][a-z]{2} \d/);
});

test("fmtDateTime and asOf use the same day-first form with a 24-hour clock", () => {
  assert.equal(fmtDateTime("2026-10-06T09:05:00Z", { tz: "UTC" }), "6 Oct 2026, 09:05");
  assert.equal(fmtDateTime("2026-10-06T09:05:07Z", { tz: "UTC", year: false, seconds: true }), "6 Oct, 09:05:07");
  assert.equal(fmtDateTime(undefined), "–");
  assert.equal(asOf("2026-10-03"), "3 Oct 2026");
  assert.equal(asOf(null), null);
});
