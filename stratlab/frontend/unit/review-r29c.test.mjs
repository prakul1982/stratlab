// Round 29C: a stored "Price is above 1.05 × Price" rule, the privacy page's Telegram wording.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { selfMultipleNote, meaningful } = await import("../src/lib/rules.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("R29C-006: a price against a multiple of the price is said to be never true, with the target or stop that was meant", () => {
  const up = { l: { t: "price" }, op: "gt", r: { t: "price", k: 1.05 } };
  const note = selfMultipleNote(up);
  assert.match(note, /"Price is above 1\.05 × Price"/);
  assert.match(note, /can't work as a rule/);
  assert.match(note, /profit target of 5% over your entry price/);
  assert.match(selfMultipleNote({ l: { t: "price" }, op: "lt", r: { t: "price", k: 0.95 } }), /stop loss of 5% under your entry price/);
  assert.equal(selfMultipleNote({ l: { t: "price" }, op: "gt", r: { t: "sma", p: 50 } }), null);
  assert.equal(selfMultipleNote({ l: { t: "price" }, op: "gt", r: { t: "price", ago: 1 } }), null);
  assert.equal(meaningful([up]).kept.length, 0);
});

test("R29C-007: /privacy names Telegram only as offered in Settings", () => {
  const src = read("src/pages/LegalPage.tsx");
  assert.equal(src.split("\n").filter((l) => l.includes("Telegram")).length, 2);
  assert.match(src, /if Telegram is offered in Settings and you connect it/);
  assert.match(src, /if it is offered in Settings and you connect it/);
  assert.match(src, /"\/privacy": "15 October 2026"/);
});
