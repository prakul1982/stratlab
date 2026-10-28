// RC-4 (28 Oct 2026): the share-price chart's script (backend/app/stock_chart.js), read as it is. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC4-006: the share-price chart labels its axis with the decimals its ticks need, and names a split, bonus or demerger in its range", () => {
  const js = read("src/../../backend/app/stock_chart.js");
  assert.match(js, /function tickFormat\(ticks\)/);
  assert.match(js, /minimumFractionDigits: d, maximumFractionDigits: d/);
  assert.doesNotMatch(js, /var plain\b|plain\.format/, "no fixed two-decimal axis");
  assert.match(js, /function adjustNote\(s\)/);
  assert.match(js, /a\.k === "demerger"/);
  assert.match(js, /not the prices traded then/);
  assert.match(js, /adjNote\.hidden = !bits\.length;/);
  assert.match(js, /adjustNote\(s\);/, "show() calls it");
  assert.ok(js.length < 14000, "still a small script");
});

test("RC4-006: the axis of a stock under ten cents, and of a small one, reads as its ticks are", () => {
  const js = read("src/../../backend/app/stock_chart.js");
  const src = /function tickFormat\(ticks\) \{[\s\S]*?\n  \}/.exec(js)[0];
  const tickFormat = new Function("loc", `${src}; return tickFormat;`)("en-US");
  const label = (ticks) => ticks.map((v) => tickFormat(ticks).format(v));
  assert.deepEqual(label([0.005, 0.01, 0.015, 0.02]), ["0.005", "0.010", "0.015", "0.020"], "0.005 steps are not rounded onto each other");
  assert.deepEqual(label([2.5, 5, 7.5, 10]), ["2.5", "5.0", "7.5", "10.0"]);
  assert.deepEqual(label([100, 150, 200]), ["100", "150", "200"], "round ticks keep none");
  assert.deepEqual(label([1000, 2000, 3000]), ["1,000", "2,000", "3,000"]);
});

test("RC4-012: a range needs its history to within a weekend, not ten days (1M was offered on 21 days of closes)", () => {
  const js = read("src/../../backend/app/stock_chart.js");
  const ranges = /var RANGES = (\{[^;]*\});/.exec(js)[1];
  const src = /function available\(r\) \{[\s\S]*?\n  \}/.exec(js)[0];
  const available = (t0, last, r) => new Function("data", "RANGES", `${src}; return available;`)({ t: [t0, last] }, new Function(`return ${ranges}`)())(r);
  const last = 20_000;
  assert.equal(available(last - 21, last, "1m"), false, "21 days is not a month");
  assert.equal(available(last - 28, last, "1m"), true, "a month less a weekend is");
  assert.equal(available(last - 31, last, "1m"), true);
  assert.equal(available(last - 150, last, "6m"), false);
  assert.equal(available(last - 366, last, "1y"), true);
  assert.equal(available(last - 300, last, "1y"), false, "ten months have no 1Y");
  assert.equal(available(last - 5, last, "all"), true);
});

test("RC4-013: a company the server has no closes for (a new listing) is told so, with no Try again; a failed read still gets one", () => {
  const js = read("src/../../backend/app/stock_chart.js");
  assert.match(js, /if \(r\.status === 404\) throw new Error\("none"\);\s*if \(!r\.ok\) throw new Error\(String\(r\.status\)\);/);
  assert.match(js, /j\.t\.length < 2\) throw new Error\("none"\)/);
  assert.match(js, /var none = err\.message === "none";[^\n]*\n\s*started = none;/, "a 404 is not asked for again by the Try again button");
  assert.match(js, /No price chart is available for this company yet\./);
  assert.match(js, /if \(none\) return;\s*var b = document\.createElement\("button"\);/, "the button is for a read that failed");
  assert.match(js, /The price chart couldn't be loaded just now\./);
  assert.ok(js.length < 14000);
});
