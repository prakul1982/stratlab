// Money space fixes from the third review, round D (frontend). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { taxHasData } = await import("../src/lib/fy.ts");
const { netWorthDelta } = await import("../src/lib/networth.ts");

const read = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("the Money home asks for tradebooks only when the tax report has nothing to work from", () => {
  assert.equal(taxHasData({ trades: 0 }), false);
  assert.equal(taxHasData({ trades: 0, business_lines: 0, mf: { count: 0 }, us_trades: 0 }), false);
  assert.equal(taxHasData({ trades: 3 }), true);
  assert.equal(taxHasData({ trades: 0, business_lines: 12 }), true);
  assert.equal(taxHasData({ trades: 0, mf: { count: 2 } }), true);
  assert.equal(taxHasData({ trades: 0, us_trades: 1 }), true);
  const home = read("pages/SpaceHomes.tsx");
  assert.match(home, /!taxHasData\(t\)/);
  assert.doesNotMatch(home, /: !t\.trades \?/);
});

test("My space net worth uses the Net worth page's change and leaves partial snapshots out of the chart", () => {
  const hist = [{ d: "2026-08-01", net: 100 }, { d: "2026-09-01", net: 120 }, { d: "2026-10-01", net: 40, partial: ["EPF"] }];
  assert.deepEqual(netWorthDelta(130, null, hist, "2026-10-14"), { change: 10, since: "2026-09-01" });   // the partial October one is passed over
  assert.equal(netWorthDelta(130, ["EPF"], hist, "2026-10-14"), null);                                    // a partial live total shows no change
  const card = read("pages/MineHome.tsx");
  assert.match(card, /netWorthDelta\(v\.totals\.net, v\.totals\.partial, hist\)/);
  assert.match(card, /hist\.filter\(\(h\) => !h\.partial\?\.length\)/);
  assert.match(card, /<Spark values=\{whole\.map/);
});

test("the cards that show Today name the stocks with no buy price, as My Holdings does", () => {
  assert.match(read("pages/MineHome.tsx"), /h\.totals\.no_cost &&[^\n]*Not in these totals: \{h\.totals\.no_cost\.symbols\.join[^\n]*except Today/);
  assert.match(read("pages/SpaceHomes.tsx"), /h\.totals\.no_cost &&[^\n]*except Today/);
  assert.match(read("pages/HoldingsPage.tsx"), /Not in these totals: \{t\.no_cost\.symbols\.join[^\n]*\n?[^\n]*except Today/);
});
