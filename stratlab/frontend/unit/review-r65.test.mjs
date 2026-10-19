// Round 65 (19 Oct 2026): plan views and the visitor's pages — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R65-001: a scrolled-back chart's older candles are kept between the minute's price refreshes too", () => {
  const src = read("src/charts/price/lazy.tsx");
  assert.doesNotMatch(src, /if \(o\.before\) return api<Answer>\(url\);/);
  assert.match(src, /return o\.before \? got : got\.then/);
});

test("R65-002: the visitor's plans are asked for again twice before 'couldn't be loaded'", () => {
  const src = read("src/lib/currency.ts");
  assert.match(src, /void read\(2\);/);
  assert.match(src, /if \(left > 0\) timer = window\.setTimeout\(\(\) => read\(left - 1\)/);
});

test("R65-005: a chain's time is named once", async () => {
  const { chainWithTime } = await import("../src/lib/positioning.ts");
  const asOf = "2026-10-19T12:29:00+05:30", t = Date.parse(asOf);
  assert.equal(chainWithTime({ source: "live", as_of: asOf }, "19 Oct, 12:29 IST", t + 10 * 60_000), "chain at 12:29 IST");
  assert.equal(chainWithTime({ source: "recorded", as_of: asOf }, "19 Oct, 12:29 IST", t), "recorded chain, 19 Oct, 12:29 IST");
});

test("R65-004, R65-005, R65-007: a visitor picks the currency; the VIX card names its chain's time once; breadth says what's locked", () => {
  assert.match(read("src/pages/Login.tsx"), /<select className="k-input" value=\{currency\} onChange=\{\(e\) => pick\(e\.target\.value\)\} aria-label="Prices in" disabled=\{!pricing\}>/);
  assert.match(read("src/components/VixPanel.tsx"), /upperFirst\(chainWithTime\(ivNow, vixTime\(ivNow\.as_of\)\)\)/);
  assert.match(read("src/pages/BreadthPage.tsx"), /Today's numbers and today's charts are on every plan\. The history charts, from 3 months back,/);
});
