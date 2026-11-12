// Market movers: each list's name and figure, a row's figure for the CSV, the count line, the page as a lazy route in Market today beside
// the Heatmap with a deep link, search words and a feature card, its plan gate (the top 5 for everyone, the rest on Basic), and facts only.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { LISTS, LIST_META, countLine, figureOf, isList, times } from "../src/lib/movers.ts";

// the app's own files import each other without ".ts"
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const ROW = { s: "AAA", n: "AAA Ltd", cap: 1000, px: 100, chg: 8, vol: 5000, avg: 1000, vx: 5, tv: 500000, hi: 120, lo: 60 };

test("six lists, each with its name and the figure it adds", () => {
  assert.deepEqual([...LISTS], ["gainers", "losers", "traded", "spikes", "highs", "lows"]);
  assert.deepEqual(LISTS.map((k) => LIST_META[k].label), ["Gainers", "Losers", "Most traded", "Volume spikes", "52-week highs", "52-week lows"]);
  assert.deepEqual(LISTS.map((k) => figureOf(k, ROW)), [5, 5, 500000, 5, 120, 60]);
  assert.ok(isList("spikes") && !isList("best") && !isList(null));
  assert.equal(times(4.06), "4.1×");
  assert.equal(times(null), "–");
});

test("a cut list says so", () => {
  assert.equal(countLine(5, 312), "The top 5 of 312");
  assert.equal(countLine(12, 12), "All 12");
  assert.equal(countLine(0, 0), "");
});

test("the page is a lazy route in Market today beside the Heatmap, with a deep link, search words, a feature card and its plan gate", async () => {
  const main = read("src/main.tsx");
  assert.match(main, /const MoversPage = page\(\(\) => import\("\.\/pages\/MoversPage"\), "MoversPage"\);/);
  assert.match(main, /<Route path="\/invest\/movers" element=\{<MoversPage \/>\} \/>/);
  assert.ok(!/^import .*MoversPage/m.test(main), "the page is loaded when opened, not with the first download");
  const { NAV, locate } = await import("../src/lib/nav.ts");
  const { isAppPath } = await import("../src/lib/deepLinks.ts");
  const at = locate("/invest/movers");
  assert.equal(at.group.id, "market-today");
  assert.equal(at.page.label, "Movers");
  assert.match(at.page.words, /gainers losers/);
  const labels = NAV.invest.groups.find((g) => g.id === "market-today").pages.map((p) => p.label);
  assert.equal(labels.indexOf("Movers"), labels.indexOf("Heatmap") + 1);
  assert.ok(isAppPath("/invest/movers"));
  assert.match(read("src/lib/features.ts"), /id: "movers", title: "Market movers",[^\n]*to: "\/invest\/movers"/);
  const { PAGE_GATES } = await import("../src/lib/gates.ts");
  assert.deepEqual(PAGE_GATES["/invest/movers"], { feature: "movers", whole: false });
  const page = read("src/pages/MoversPage.tsx");
  assert.match(page, /csv=\{locked \? undefined :/);                                // no CSV on the teaser
  assert.match(page, /disabled=\{locked\}/);                                         // nor the filters
  assert.match(page, /<PlanNote plan="basic">/);
  assert.match(page, /<Working /);
  assert.match(page, /import "\.\/movers\.css";/);
  assert.ok(!read("src/styles.css").includes(".mv-"), "the page's CSS stays out of the first download's stylesheet");
});

test("Help links the public data status page", () => {
  assert.match(read("src/pages/AppGates.tsx"), /<a className="k-linkcard" href="\/status"><b>Data status<\/b>/);
});

test("facts only: no advice words and no data source's name on the page", () => {
  const text = read("src/pages/MoversPage.tsx") + read("src/lib/movers.ts");
  const quoted = [...text.matchAll(/"([^"\n]{12,})"|`([^`\n]{12,})`|>([^<>{}\n]{12,})</g)].map((m) => m[1] ?? m[2] ?? m[3]).join("\n");
  assert.ok(!/\b(buy|sell|hold|accumulate|avoid|cheap|expensive|bullish|bearish|should|recommend|best)\b/i.test(quoted), quoted.match(/\b(buy|sell|hold|accumulate|avoid|cheap|expensive|bullish|bearish|should|recommend|best)\b/i)?.[0]);
  assert.ok(!/kite|zerodha|yahoo|screener\.in|finnhub|edgar|nseindia/i.test(text));
});
