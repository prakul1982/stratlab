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

test("VR6-013: each plan card shows about 400 characters of its lines and folds the rest; every line is still on the page", async () => {
  const { FEATURES, splitFeatures, CARD_TEXT_BUDGET } = await import("../src/lib/plans.ts");
  assert.equal(CARD_TEXT_BUDGET, 400);
  const visible = {};
  for (const p of ["free", "basic", "pro"]) {
    const { head, shown, more } = splitFeatures(FEATURES[p]);
    assert.deepEqual([...head, ...shown, ...more].sort(), [...FEATURES[p]].sort());                  // nothing lost
    assert.ok(shown.length >= 3 && more.length >= 1, `${p}: ${shown.length} shown, ${more.length} folded`);
    visible[p] = shown.reduce((n, l) => n + l.length, 0);
  }
  // by words the three are about as long as each other (five lines each was 285, 405 and 325px of text)
  assert.ok(Math.max(...Object.values(visible)) - Math.min(...Object.values(visible)) < 150, JSON.stringify(visible));
  const long = ["x".repeat(200), "y".repeat(200), "z".repeat(200), "w".repeat(200), "v".repeat(200)];
  assert.deepEqual([splitFeatures(long).shown.length, splitFeatures(long).more.length], [3, 2]);          // never fewer than three, though three pass the budget
  assert.deepEqual([splitFeatures(["a", "b"]).shown.length, splitFeatures(["a", "b"]).more.length], [2, 0]);   // a short card folds nothing
  const src = read("src/pages/PlansPage.tsx");
  assert.match(src, /const \{ head, shown, more \} = splitFeatures\(FEATURES\[p\]\);/);
  assert.match(src, /<details className="k-plan-more" data-testid=\{`plan-more-\$\{p\}`\}>/);
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

test("VR6-018: the chart's view buttons join the scale buttons under the chart (VR7-010: on a phone too, they were alone on a third line of a 360px toolbar)", () => {
  const src = read("src/charts/price/PriceChart.tsx");
  assert.doesNotMatch(src, /\{phone && viewButtons\}/);
  assert.match(src, /<div className="pc-foot-r">\s*\{viewButtons\}/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-foot-r \{ display: flex; flex-wrap: wrap;/);
});

test("VR6-020: link rows and small buttons are 44px to the thumb on a phone without a taller list (the link keeps its place, its box grows)", () => {
  const css = read("src/styles.css");
  const block = css.slice(css.indexOf("/* VR6-020"));
  assert.match(block, /\.k-page a\.link, a\.link\.k-small, a\.link\.k-any, \.k-spread > a\.link, \.h-filing a\.link \{ padding-block: 12px; margin-block: -4px; \}/);
  assert.match(block, /a\.tap-link, \.mine-tl-i \.body a \{ min-height: 44px; margin-block: -6px; \}/);
  assert.match(block, /\.link-btn\.inr-pick, body \.k-search input \{ min-height: 44px; \}/);
  assert.match(css, /\.ch-bar \.ch-btn, \.ch-bar \.ch-seg button \{ min-height: 44px; \}/);
});

test("VR6-023: a figure too long for half a line (an eight-digit rupee total) is tried a size down before the figures go one under another", () => {
  const src = read("src/components/kit/Stat.tsx");
  assert.match(src, /if \(wraps\) \{ el\.classList\.add\("tight"\); wraps = wrapping\(\); \}/);
  assert.match(src, /el\.classList\.remove\("duo", "tight"\)/);
  assert.match(read("src/styles.css"), /\.k-stats\.duo\.tight \.k-stat-v \{ font-size: 22px; \}/);
});

test("VR6-024: a phone shows twelve strategy cards, ten positions and eight dividends at a time, with Show more", () => {
  const lib = read("src/pages/LibraryPage.tsx");
  assert.match(lib, /export const PHONE_CARDS = 12;/);
  assert.match(lib, /\(phone \? rows\.slice\(0, PHONE_CARDS \* cardPages\) : rows\)\.map/);
  assert.match(lib, /data-testid="lib-show-more"/);
  assert.match(read("src/pages/HoldingsPage.tsx"), /<DataTable label="Positions".*stack phonePage=\{10\} \/>/);
  const act = read("src/components/HoldingsActions.tsx");
  assert.match(act, /rows=\{data\.ahead\} rowKey=\{key\} stack phonePage=\{8\}/);
  assert.match(act, /rows=\{received\} rowKey=\{key\} stack phonePage=\{8\}/);
});
