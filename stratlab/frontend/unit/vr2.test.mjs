// VR2 (27 Oct 2026): the second visual review of the 25 pages people use most: what the CSS and the pages now say.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("VR2-001, VR2-002: the tool tiles and the watchlist tiles of one row are as tall as each other", () => {
  assert.doesNotMatch(css, /\.k-explore \.explore-grid \{[^}]*align-items: start/);
  assert.doesNotMatch(css, /\.space-panels \.inv-tiles \{ align-items: start; \}/);
});

test("VR2-003: Money home's holdings card does not carry the date in its day label; the tax link is short (the page's own name)", () => {
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /label=\{h\.totals\.session && h\.totals\.session < istToday\(\) \? "Last session" : "Today"\}/);
  assert.match(home, />Tax report →<\/Link>/);
});

test("VR2-004, VR2-005: the watchlist says its day once; an Open button stays at the card head's top right", () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.match(mine, /const sameDay = days\.length > 1 && days\[0\] && days\.every\(\(d\) => d === days\[0\]\) \? days\[0\] : null;/);
  assert.match(mine, /\{!sameDay && \(\(\) => \{ const d = day\(m\)/);
  assert.match(mine, /Prices from \{fmtDate\(sameDay,/);
  assert.match(css, /\.mine-tl-i \.body \.k-stat-d \{ display: -webkit-box; -webkit-line-clamp: 1;/);   // six events and six movers are about as tall
  assert.match(css, /\.mine-slot \.k-card-head:has\(> \.k-card-actions > a:only-child\) \{ flex-wrap: nowrap;/);
});

test("VR2-006, VR2-007: market events are two to a row; Key numbers' last row fills its width", () => {
  assert.match(read("src/pages/trade/events.css"), /\.ev-weekgrid > \.ev-week \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(260px, 1fr\)\);/);
  const inv = read("src/styles-invest.css");
  assert.match(inv, /\.inv-metrics > :last-child:nth-child\(3n\+1\) \{ grid-column: span 6; \}/);
  assert.match(inv, /\.inv-metrics > :nth-last-child\(2\):nth-child\(3n\+1\), \.inv-metrics > :last-child:nth-child\(3n\+2\) \{ grid-column: span 3; \}/);
});

test("VR2-008: a long usage value on Account takes the whole row", () => {
  // (VR6-014: usageSpans also widens a row that would stand alone beside an empty cell)
  assert.match(read("src/pages/AccountPage.tsx"), /usageSpans\(usage\.map\(\(\[, v\]\) => v\.length > 44\)\)\.map\(\(wide, i\) => <div key=\{usage\[i\]\[0\]\} className=\{wide \? "wide" : undefined\}>/);
  assert.match(css, /\.k-rows\.two > div\.wide \{ grid-column: 1 \/ -1; \}/);
});

test("VR2-009, VR2-010, VR2-011: a wrapping chip row keeps + Custom in the row; phone segments are equal; a leg's remove is a labelled button", () => {
  assert.match(css, /\.k-chiprow\.wrap > \.k-chipbar \{ display: contents; \}/);
  assert.match(css, /\.k-seg:not\(\[data-stack\]\) button \{ flex: 1 1 0; \}/);
  assert.match(read("src/pages/trade/options.css"), /td\[data-label="Remove"\] \.chip-x::after \{ content: "Remove leg"; \}/);
});
