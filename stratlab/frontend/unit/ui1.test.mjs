// Lane ui1 (owner, 18 Nov). Item 6 ("fix ui dude", the Themes page): one line under the title, the box and "Map it" on one row with the market
// switch, the shared library as equal chips with short names (at most two rows, then "All N themes"), the ideas folded under it.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a theme's chip says its short name: the words before a bracket or a dash that explain it", async () => {
  const { shortTheme } = await import("../src/lib/themeFormat.ts");
  assert.equal(shortTheme("Utilities (Indian power, gas and water-linked infrastructure)"), "Utilities");
  assert.equal(shortTheme("Pharmaceuticals (generic drug makers and APIs)"), "Pharmaceuticals");
  assert.equal(shortTheme("Defence — aerospace and shipyards"), "Defence");
  assert.equal(shortTheme("Cement"), "Cement");
  assert.equal(shortTheme("EV and battery supply chain"), "EV and battery supply chain");
  assert.equal(shortTheme("(odd)"), "(odd)");
});

test("the Themes page: one-line lede with the method behind the (i); box, Map it and market switch in one form row", () => {
  const page = read("src/pages/ThemesPage.tsx");
  const lede = page.match(/lede="([^"]*)"/)[1];
  assert.ok(lede.length <= 80, `the lede is one line (${lede.length} chars)`);
  assert.match(page, /infoLabel="How a theme is mapped"/);
  assert.match(page, /<form className="theme-map" aria-label="Map a theme"[^\n]*\n\s*<RegionSwitch region=\{region\} setRegion=\{setRegion\} \/>\s*<div className="theme-field">/);
  const css = read("src/styles.css");
  assert.match(css, /\.theme-field \{ flex: 1 1 320px; display: flex; align-items: center;/);
  assert.match(css, /\.theme-ready \{ display: grid; grid-template-columns: repeat\(auto-fill, minmax\(180px, 1fr\)\);/);
});

test("Ready to open: short names (full name and date in the title), two rows of the grid's columns, then All N themes", () => {
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /title=\{libraryLabel\(i, \(d\) => fmtDate\(d, \{ year: false \}\), false\)\}/);
  assert.match(page, /<span>\{shortTheme\(i\.name\)\}<\/span>/);
  assert.match(page, /const room = cols \* 2;/);
  assert.match(page, /const shown = more \? items\.slice\(0, room - 1\) : items;/);
  assert.match(page, /All \{items\.length\} themes/);
  assert.match(page, /<Disclosure summary="More ideas"/);
});

// item 3 (owner, 18 Nov: HDFC Bank's update filings, "NSE filing ↗" dropped to its own line under a long subject)
test("update filings: the same subject filed again is one row with its other days, in the list's order", async () => {
  const { foldFilings } = await import("../src/lib/biz.ts");
  const lodr = "Intimation under SEBI (LODR) Regulations, 2015";
  const rows = [{ id: 1, title: lodr }, { id: 2, title: "Business update Q2" }, { id: 3, title: `${lodr} ` }, { id: 4, title: "INTIMATION UNDER SEBI (LODR) REGULATIONS, 2015" }, { id: 5, title: "Business update Q1" }];
  const g = foldFilings(rows);
  assert.deepEqual(g.map((x) => x.items.map((i) => i.id)), [[1, 3, 4], [2], [5]]);
  assert.equal(g[0].title, lodr);
});

test("update filings: date | subject (two lines at most) | link on one grid; five rows, then Show all N", () => {
  const panel = read("src/components/BizUpdates.tsx"), css = read("src/styles.css");
  assert.match(panel, /const FILINGS_FIRST = 5;/);
  assert.match(panel, /const groups = foldFilings\(v\.filings\);/);
  assert.match(panel, /Show all \{groups\.length\}/);
  assert.match(panel, /<span className="biz-title" title=\{title\}>\{title\}<\/span>/);
  assert.match(css, /\.biz-title \{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; \}/);
  assert.match(css, /\.biz-link \{ white-space: nowrap; justify-self: end; \}/);
});
