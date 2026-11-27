// ui100: the launch audit's rules (live site, 27 Nov). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { perShare } = await import("../src/lib/format.ts");
const { snapWidth } = await import("../src/lib/phoneFit.ts");
const { placeTrail, placeName, locate } = await import("../src/lib/nav.ts");
const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");

test("an amount a share has the decimals it needs, never trailing zeros past the second", () => {
  assert.equal(perShare(0.75, "INR"), "₹0.75");          // the Calendar said "₹0.7500 a share"
  assert.equal(perShare(0.0125, "INR"), "₹0.0125");
  assert.equal(perShare(0.105, "INR"), "₹0.105");
  assert.equal(perShare(6, "INR"), "₹6.00");
  assert.equal(perShare(5.5, "INR"), "₹5.50");
  assert.equal(perShare(0.27, "USD"), "$0.27");
  assert.equal(perShare(null, "INR"), "–");
  for (const f of ["lib/calendarRows.ts", "components/CorpActions.tsx"]) assert.doesNotMatch(src(f), /amount < 1 \? 4 : 2/, f);
});

test("a period grid scrolled to its end starts on a whole column", () => {
  // period columns start every 100 px after the names' 180 px column; scrolled 470 px, the view's edge past the names is at 650, inside the
  // column starting at 580, whose last 30 px show beside the names: the names' column grows 30 px
  const starts = [180, 280, 380, 480, 580, 680, 780, 880];
  assert.equal(snapWidth(starts, 180, 470), 30);           // edge at 650, next column at 680
  assert.equal(snapWidth(starts, 180, 500), 0);            // the view starts on a column's edge
  assert.equal(snapWidth(starts, 180, 0), 0);              // not scrolled: nothing under the names
  assert.equal(snapWidth([], 180, 300), 0);
});

test("the Coming up card's way to the Calendar is the size of the other cards' head links", () => {
  assert.match(src("pages/SpaceHomes.tsx"), /<Link to=\{to\} className="link" data-testid="see-calendar">See calendar →<\/Link>/);
});

test("a notebook's card on Trade keeps its name readable: the verdict under it, never beside it squeezing it", () => {
  assert.match(css, /\.space-recent-row \{ display: flex; flex-direction: column;/);
  assert.match(css, /\.space-recent-name \{[^}]*-webkit-line-clamp: 2/);
});

test("a fit table keeps a column of short words on one line", () => {
  assert.match(css, /\.k-tbl-wrap\.k-fit \.k-table :is\(td, th\)\[data-keep\] \{ white-space: nowrap; \}/);
  assert.match(src("components/kit/DataTable.tsx"), /if \(fit && b\) keepShort\(b\);/);
});

test("a card title made of parts flows as one line of words", () => {
  assert.match(src("components/kit/Card.tsx"), /<span className="k-card-title-text">\{title\}<\/span>/);
});

test("two charts side by side line up their plots", () => {
  assert.match(css, /\.k-two > \.pos-chart \{ justify-content: space-between; \}/);
});

test("a page's place names each part once", () => {
  assert.equal(placeTrail(["Invest", "Calendar", "Calendar"]), "Invest › Calendar");     // Help and search said "Calendar › Calendar"
  assert.equal(placeTrail(["Trade", "Calendar", "Market events & expiries"]), "Trade › Calendar › Market events & expiries");
  assert.equal(placeName(locate("/calendar")), "Calendar");
  assert.match(src("pages/AppGates.tsx"), /placeTrail\(\[NAV\[l\.space\]\.label/);
});

test("an index notice whose day has passed is an earlier change, not above the one coming up", () => {
  const page = src("pages/trade/EventsPage.tsx");
  assert.match(page, /const past = \(c: IndexChange\) => !!c\.effective && c\.effective < today;/);
  assert.match(page, /const unread = unreadAll\.filter\(\(c\) => !past\(c\)\), unreadPast = unreadAll\.filter\(past\);/);
});
