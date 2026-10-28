// FIX-1A: the findings of the live-site review LIVE-1A (trade and invest, 28 Oct 2026). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE1A-048/049: the compare page's qualifier is one numbered note under its table, and the AI read comes after the figures", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /<sup className="cmp-foot-mark"/);
  assert.match(r, /className="k-note cmp-foots" data-testid="cmp-note"/);
  // the AI card is drawn after "The numbers side by side"
  assert.ok(r.indexOf('<CardHead title="AI comparison" />') > r.indexOf('<CardHead title="The numbers side by side" />'));
  assert.match(read("src/charts/price/PriceChart.tsx"), /data-testid="pc-cmp-since"/);
  assert.match(read("src/styles.css"), /\.cmp-foots \{[^}]*overflow-wrap: anywhere/);
});

test("LIVE1A-051/006: a gap in points is readable, and a run of too few trades leads with that verdict", async () => {
  const { readablePoints, verdictLines } = await import("../src/lib/tradeUi.ts");
  assert.equal(readablePoints("11438.7 points behind buy and hold after costs."), "11,439 points behind buy and hold after costs.");
  assert.equal(readablePoints("3.8 points ahead of buy and hold after costs."), "3.8 points ahead of buy and hold after costs.");
  assert.equal(readablePoints("62.5 points behind."), "62.5 points behind.");
  const few = verdictLines("3.8 points ahead of buy and hold after costs; only 9 trades: too few to judge.", "not_enough");
  assert.deepEqual(few, { main: "Only 9 trades: too few to judge.", checks: "3.8 points ahead of buy and hold after costs.", swapped: true });
  const lost = verdictLines("Within a point of buy and hold after costs; lost money after costs.", "no_edge");
  assert.equal(lost.main, "Lost money after costs.");
  // a run that made money keeps the comparison first
  const ok = verdictLines("44.5 points ahead of buy and hold after costs; 4 of 4 checks run · 2 passed.", "mixed");
  assert.deepEqual(ok, { main: "44.5 points ahead of buy and hold after costs.", checks: "4 of 4 checks run · 2 passed.", swapped: false });
  assert.match(read("src/styles.css"), /\.verdict-head \{[^}]*line-height: 1\.05/);
});

test("LIVE1A-060/061: a US session still going on is not a close, and the banner names no company or error code", async () => {
  const { problemNote } = await import("../src/lib/ipoText.ts");
  const t = problemNote(["SEC filings for Amaero Inc.: The SEC is having trouble (500)."], "28 Oct, 12:00");
  assert.doesNotMatch(t, /Amaero|500|trouble/);
  assert.match(t, /filings couldn't be read/);
  assert.match(problemNote(["12 Sep calendar: timeout"], null), /a source couldn't be read/);
  assert.match(read("src/pages/IposPage.tsx"), /problemNote\(d\.problems/);
});

test("LIVE1A-029/030/031: bids say when they were read, the issue size shows its two parts, and unpriced listings fold away", () => {
  const p = read("src/pages/IposPage.tsx");
  assert.match(p, /data-testid="ipo-sub-at"/);
  assert.match(p, /counting the bids placed on both exchanges/);
  assert.match(p, /data-testid="ipo-size-parts"/);
  assert.match(p, /testId="ipo-unpriced"/);
});

test("LIVE1A-005/007/008/036: the verdict page's numbers and costs are full-width cards, its header wraps whole, its menus fit and the next steps stack on a phone", () => {
  const e = read("src/pages/ExperimentPage.tsx"), t = read("src/pages/trade/trade.css"), s = read("src/styles.css");
  assert.match(e, /className="k-rows two" role="list" aria-label="Profit and costs"/);
  assert.match(t, /\.k-money\.k-money-even \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(e, /className="k-toolbar next-steps"/);
  assert.match(t, /\.next-steps \{ flex-direction: column; align-items: stretch; \}/);
  assert.match(e, /label: `Compare with v\$\{Math\.max\(\.\.\.prev\)\}`/);
  assert.match(s, /\.more-pop \{[^}]*width: max-content/);
  assert.match(e, /className="link back-link"/);
});

test("LIVE1A-001/052: on a desktop window the Lab notes tab is an edge handle in the page's margin", () => {
  const s = read("src/styles.css");
  const i = s.indexOf("@media (min-width: 1100px) {\n  .ln-btn");
  assert.ok(i > 0);
  assert.match(s.slice(i, i + 700), /\.ln-btn \{ position: fixed; right: 0;/);
});
