// VR-6 (28 Oct 2026): the harsh visual review after PUB-2 and of the most-used pages. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the source's own imports have no .ts ending
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { slotSpans } = await import("../src/lib/mineLayout.ts");
const { usageSpans } = await import("../src/lib/account.ts");

test("VR6-010: an empty watchlist takes a row of its own on My space, and Coming up widens to fill the row before it", () => {
  const all = ["networth", "pnl", "paper", "markets", "coming", "watch"];
  assert.deepEqual([slotSpans(all).coming, slotSpans(all).watch], [7, 5]);                       // beside each other as before
  const alone = slotSpans(all, ["watch"]);
  assert.deepEqual([alone.coming, alone.watch], [12, 12]);
  assert.deepEqual([alone.networth, alone.pnl, alone.paper, alone.markets], [slotSpans(all).networth, slotSpans(all).pnl, slotSpans(all).paper, 12]);
  // the watchlist first in the order: it is alone, and the two after it share their row
  const first = slotSpans(["watch", "coming", "markets"], ["watch"]);
  assert.deepEqual([first.watch, first.coming, first.markets], [12, 12, 12]);
  const src = read("src/pages/MineHome.tsx");
  assert.match(src, /slotSpans\(shown, watchItems !== null && watchItems\.length === 0 \? \["watch"\] : \[\]\)/);
});

test("VR6-011: the Invest home stacks its three cards when nothing is watched, instead of a one-line card beside two tall ones", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.match(src, /const nothingWatched = watching !== null && !watching\.some\(\(w\) => w\.region === region\);/);
  assert.match(src, /className=\{nothingWatched \? "space-col" : "grid2 space-panels"\}/);
});

test("VR6-012: with fewer than three snapshots the list sits inside the totals card, not in a card of its own with one line", () => {
  const src = read("src/pages/money/NetWorthPage.tsx");
  assert.doesNotMatch(src, /snapsList\("k-card nw-snaps"\)/);
  assert.match(src, /whole\.length < 3 && snapsList\("nw-snaps"\)\}\n\s*<\/Card>/);
  // VR6-015: "My Holdings: Indian stocks · Indian stocks": a kind is not said again when the name ends with it
  assert.match(src, /!r\.name\.endsWith\(r\.label\) && <span className="k-note"> · \{r\.label\}<\/span>/);
});

test("VR6-013: each plan card shows five lines and folds the rest; every line is still on the page", () => {
  const src = read("src/pages/PlansPage.tsx");
  assert.match(src, /export const PLAN_LINES_SHOWN = 5;/);
  assert.match(src, /items\.slice\(0, PLAN_LINES_SHOWN\)/);
  assert.match(src, /<details className="k-plan-more" data-testid=\{`plan-more-\$\{p\}`\}>/);
  assert.match(src, /items\.slice\(PLAN_LINES_SHOWN\)\.map\(line\)/);
  assert.match(read("src/styles.css"), /\.k-plan-more summary \{[^}]*min-height: 44px;/);
});

test("VR6-014: the usage list on Account never leaves a row alone beside an empty cell", () => {
  // thirteen rows, the first and the fourth long: the last one (alone in its line) takes the whole line
  const long = [true, false, false, true, false, false, false, false, false, false, false, false, false];
  const got = usageSpans(long);
  assert.equal(got[0], true); assert.equal(got[3], true);
  assert.equal(got.length - 1, 12); assert.equal(got[12], true);                                  // the 2 short rows after the first pair up, then 9 more: the odd thirteenth is alone
  assert.deepEqual(usageSpans([false, false, false, false]), [false, false, false, false]);       // an even count pairs up: nothing widens
  assert.deepEqual(usageSpans([false, false, false]), [false, false, true]);
  // a long row after a single short one: the short one takes its line (no empty cell before the long one)
  assert.deepEqual(usageSpans([false, false, false, true]), [false, false, true, true]);
});

test("VR6-016: four figures on a phone are two and two on the Money home", () => {
  assert.match(read("src/styles.css"), /@media \(max-width: 640px\) \{ \.money-panels \.k-stats:has\(> \.k-stat:nth-child\(4\):last-child\) \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \} \}/);
});

test("VR6-017: an empty Paper sessions card on My space has the shape of its neighbours and still offers the next step", () => {
  const src = read("src/pages/MineHome.tsx");
  assert.match(src, /<CardHead title="Paper sessions" \/>\n\s*<Stat label="Running now" value="None running"/);
  assert.match(src, /<Link className="btn sm" to="\/paper">Start paper trading<\/Link>/);
});

test("VR6-018: on a wide screen the chart's view buttons join the scale buttons under the chart; on a phone they stay in the bar", () => {
  const src = read("src/charts/price/PriceChart.tsx");
  assert.match(src, /\{phone && viewButtons\}/);
  assert.match(src, /<div className="pc-foot-r">\s*\{!phone && viewButtons\}/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-foot-r \{ display: flex; flex-wrap: wrap;/);
});
