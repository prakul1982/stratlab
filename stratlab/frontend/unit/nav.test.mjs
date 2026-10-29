// The menu's one map (lib/nav.ts): every page is in exactly one group, addresses find their page, and search knows the
// everyday words. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { ALL_PAGES, NAV, groupPath, locate, locateGroup } = await import("../src/lib/nav.ts");
const { match } = await import("../src/lib/features.ts");
const { cleanLayout } = await import("../src/lib/mineLayout.ts");

test("the map has the owner's menu entries, in order (IA-1: 42 entries became 14, each a page of tabs)", () => {
  assert.deepEqual(NAV.trade.groups.map((g) => g.label), ["Strategies", "Practise", "F&O desk", "Trade journal", "Calendar"]);
  assert.deepEqual(NAV.invest.groups.map((g) => g.label), ["Companies", "Find stocks", "Themes", "Market today", "Market data", "Calendar", "Watchlist"]);
  assert.deepEqual(NAV.money.groups.map((g) => g.label), ["Portfolio", "Tax", "Plan", "Calendar"]);
  assert.deepEqual(NAV.invest.groups.find((g) => g.id === "find-stocks").pages.map((p) => p.label), ["Figures", "Chart rules", "Filings"]);
  assert.deepEqual(NAV.invest.groups.find((g) => g.id === "market-today").pages.map((p) => p.label), ["Mood", "Breadth", "Sectors", "Flows", "Today's brief"]);
  assert.deepEqual(NAV.invest.groups.find((g) => g.id === "market-data").pages.map((p) => p.label), ["ETF vs NAV", "Margin funding", "Stock lending fees"]);
  // nothing removed: the 42 pages the menu had, plus Flows and the Calendar's All dates
  assert.equal(ALL_PAGES.length, 44);
});

test("each page has one address, a one-liner and a place", () => {
  const seen = new Set();
  for (const { page, group, space } of ALL_PAGES) {
    assert.ok(!seen.has(page.to), `${page.to} listed twice`);
    seen.add(page.to);
    assert.ok(page.line.length > 10 && page.blurb.length > 10, `${page.label} needs its lines`);
    assert.equal(locateGroup(groupPath(space, group)).group.id, group.id);
  }
});

test("addresses find their page, including the ones that were tabs", () => {
  assert.equal(locate("/research/IN/RELIANCE").page.label, "Look up a company");
  assert.equal(locate("/research/IN/RELIANCE/deep").page.label, "Look up a company");
  assert.equal(locate("/research/investor").page.label, "Stocks");          // IA-1: the Watchlist entry's Stocks tab
  assert.equal(locate("/trade/positioning/stocks").page.label, "Positioning");
  assert.equal(locate("/n/abc/e/3").page.label, "Notebooks");
  assert.equal(locate("/trade/signals/xyz").page.label, "Forward test");
  assert.equal(locate("/invest/margin-funding?x=1").group.label, "Market data");
  assert.equal(locate("/account"), null);
  // the old groups' own pages open the entry that took each over
  assert.equal(locateGroup("/trade/g/build-and-test").group.id, "strategies");
  assert.equal(locateGroup("/invest/g/market-view").group.id, "market-today");
  assert.equal(locateGroup("/invest/g/company-news").group.id, "calendar");
  assert.equal(locateGroup("/money/g/what-you-own").group.id, "portfolio");
});

test("search finds a page by its everyday words", () => {
  assert.equal(match("MTF", 1)[0].to, "/invest/margin-funding");
  assert.equal(match("borrowed money", 1)[0].to, "/invest/margin-funding");
  assert.equal(match("slb", 1)[0].to, "/invest/stock-lending");
  assert.equal(match("all features", 1)[0].to, "/features");
  for (const { page } of ALL_PAGES) assert.ok(match(page.label, 3).some((f) => f.to === page.to), `${page.label} is not found by its own name`);
});

test("a saved My space layout is made safe", () => {
  const l = cleanLayout({ order: ["coming", "nope", "coming", "markets"], hidden: ["paper", "x"] });
  assert.deepEqual(l.order.slice(0, 2), ["coming", "markets"]);
  assert.equal(l.order.length, 6);
  assert.deepEqual(l.hidden, ["paper"]);
  assert.equal(cleanLayout(null).order.length, 6);
});
