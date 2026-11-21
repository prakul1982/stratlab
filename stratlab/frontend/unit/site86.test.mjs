import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as S from "../src/lib/scrollRows.ts";

// site86 (Release 86), the owner's scroll request (21 Nov: "it doesn't show all the stocks; add a scroll, don't extend it, and do it everywhere"):
// the shared scroll list's arithmetic and its contract. The pages are proved in the browser (e2e/site86.spec.ts).
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// (changed on purpose, site87, owner: "it works on screen size, how much of the block a person can see on screen. Then you give a scroll": the
// row counts (6 rows, 8 on a phone, 15 for a table) are replaced by the screen's room; unit/site87.test.mjs pins the new arithmetic)
test("scrollCut: a list that fits its room doesn't scroll; past it the box is the bottom of the last whole row, never mid-row", () => {
  const rows = Array.from({ length: 20 }, (_, i) => 50.4 * (i + 1));     // each row's bottom edge
  assert.equal(S.scrollCut(rows.slice(0, 6), 400).over, false);
  const c = S.scrollCut(rows, 400);
  assert.equal(c.over, true);
  assert.equal(c.fit, Math.ceil(50.4 * 7));
  const mixed = [60, 100, 170, 210, 290, 330, 400, 470, 520, 600];
  assert.equal(S.scrollCut(mixed, 340).fit, 330);
});

test("scrollCut with the room a card gives: the most whole rows that fit, at least the floor", () => {
  const rows = Array.from({ length: 20 }, (_, i) => 50 * (i + 1));
  assert.equal(S.scrollCut(rows, 380).fit, 350);
  assert.equal(S.scrollCut(rows, 351).fit, 350);       // a pixel's rounding is not a cut row
  assert.equal(S.scrollCut(rows, 90).fit, 50);         // (changed on purpose, site87: never taller than its room; FLOOR_ROWS applies beside a shorter card)
  assert.equal(S.scrollCut(rows, 0).over, false);      // no room measured yet: drawn whole
});

test("the fade is there while more is below and gone at the end", () => {
  assert.equal(S.moreBelow(0, 300, 900), true);
  assert.equal(S.moreBelow(599, 300, 900), false);
  assert.equal(S.moreBelow(597, 300, 900), true);
  assert.equal(S.PHONE_Q, "(max-width: 640px)");
});

test("ScrollList: one shared component, sized with watchSize, named and focusable only while it scrolls", () => {
  const src = read("src/components/kit/ScrollList.tsx");
  assert.doesNotMatch(src, /new ResizeObserver\(/);                                   // R7T-014
  assert.match(src, /watchSize\(el, run\)/);
  assert.match(src, /role=\{over \? "region" : undefined\} aria-label=\{over \? label : undefined\} tabIndex=\{over \? 0 : undefined\}/);
  assert.match(src, /el\.addEventListener\("scroll", more, \{ passive: true \}\)/);
  // a long list gives way to a shorter neighbour whose content fits (changed on purpose, site87: within the screen's room)
  assert.match(src, /if \(peer !== null && bottoms\.length\) avail = Math\.min\(avail, Math\.max\(Math\.floor\(peer - head - below\)/);
  assert.match(read("src/components/kit/index.ts"), /export \{ ScrollList, useScrollRows \} from "\.\/ScrollList";/);
  // the kit's tables use it (changed on purpose, site87: past the screen's room, not TABLE_ROWS; a phone's cards and the Library too)
  const dt = read("src/components/kit/DataTable.tsx");
  assert.match(dt, /useScrollRows\(box, \{ items: bodyRows, onEnd: loadMore \}\);/);
});

test("the scroll's look: whole rows, a thin themed scrollbar, the fade, the focus ring, overscroll contained, sticky table header", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-scroll\[data-over\], \.k-tbl-wrap\[data-over\], \.k-tbl-wrap\.pinhead\[data-over\] \{ overflow-y: auto; overscroll-behavior-y: contain; scrollbar-width: thin; scrollbar-color: var\(--line-2\) transparent; \}/);
  assert.match(css, /\.k-scroll\[data-more\] \{ -webkit-mask-image: linear-gradient\(to bottom, #000 calc\(100% - 32px\), transparent\);/);
  assert.match(css, /\.k-scroll:focus-visible \{ outline-offset: -2px;/);
  assert.match(css, /\.k-scroll \{ position: relative; \}/);          // rows scrolled away never make the page taller
  assert.match(css, /\.k-scroll-box\[data-over\] \{ flex: 1 0 auto; height: var\(--k-scroll-in, auto\); \}/);
  assert.match(css, /\.k-tbl-wrap\[data-over\]:not\(\.stack\) \.k-table thead th, \.k-tbl-wrap\.pinhead\[data-over\] \.k-table thead th \{ position: sticky; top: 0;/);
  // in the public kit's file (DataTable is there), not a chunk of its own or boot.js (review-r5's budgets)
  assert.match(read("vite.config.ts"), /ReportFigure\|ScrollList\)\\\.tsx\|lib\[\\\\\/\]\(sections\|persist\|lockSlot\|resize\|scrollRows\)\\\.ts\)\$\//);
  assert.doesNotMatch(read("public/boot.js"), /k-scroll|ScrollList/);
});

test("/mine: every watchlist stock and every date, each list scrolling in its card; the cards level (replaces R85's row-count rule)", () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.match(mine, /const coming = useComingUpAll\(later\);/);
  assert.match(mine, /<ScrollList label="Your watchlist, every stock" testId="mine-watch-list">/);
  assert.match(mine, /<ScrollList label="Coming up, every date" testId="mine-coming-list">/);
  assert.match(mine, /const q = await researchApi\.quotesAll\(r, mine\.map\(\(w\) => w\.symbol\)\);/);
  assert.doesNotMatch(mine, /slice\(0, 6\)|slice\(0, 24\)|more in the calendar/);
  assert.doesNotMatch(read("src/styles.css"), /\.mine-slot\[data-card="coming"\], \.mine-slot\[data-card="watch"\] \{ align-self: start; \}/);
  assert.match(read("src/lib/research.ts"), /quotesAll: \(r: Region, syms: string\[\]\) => Promise\.all\(Array\.from\(\{ length: Math\.ceil\(syms\.length \/ 24\) \}/);
});

test("the sweep: lists that cut items off now scroll inside their cards", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /<WatchTable region=\{region\} symbols=\{mine\.map\(\(w\) => w\.symbol\)\}/);      // (changed on purpose, site87: no row count)
  assert.match(read("src/pages/SpaceHomes.tsx"), /<ScrollList label="Red flags filed lately">/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /<ScrollList label="Index notices not read into stocks"><ul className="k-list plain">\n\s+\{unread\.map/);
  assert.match(read("src/components/Research.tsx"), /<ScrollList label="Headlines" rows=\{limit\}><div className="inv-news">\n\s+\{sorted\.map/);
  assert.match(read("src/pages/trade/JournalPage.tsx"), /<ScrollList label="Lines that couldn't be read" rows=\{8\}>/);
  assert.doesNotMatch(read("src/pages/admin/LibrarySection.tsx"), /and \{d\.gate\.dropped_n - 3\} more/);
});

test("ui-lint R30: two cards side by side the same height; no count of hidden items with nothing to press; no rows cut by a box that doesn't scroll", () => {
  const rules = read("e2e/ui-lint-rules.ts"), spec = read("e2e/ui-lint.spec.ts");
  assert.match(rules, /if \(Math\.abs\(d\) > 2\) add\("R30"/);
  assert.match(rules, /counts items the list leaves out, with no scroll or link to them/);
  assert.match(rules, /rows cut off below a box that doesn't scroll/);
  assert.match(spec, /R30: "Uneven pair, hidden items or a block not sized to the screen/);      // (changed on purpose, site87)
});
