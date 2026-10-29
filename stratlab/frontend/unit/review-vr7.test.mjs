// VR-7 (28 Oct 2026): the visual review that put the phone first and looked at Market Watch. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("VR7-001: on a phone the chart's range buttons are two rows of four and the scale buttons one row, every one 44px or more each way", () => {
  const css = read("src/charts/price/priceChart.css");
  const phone = css.slice(css.indexOf("VR7-001"));
  assert.match(phone, /\.pc-foot \.pc-seg \.pc-btn \{ flex: 1 1 0; min-width: 44px;/);
  assert.match(phone, /\.pc-seg\[aria-label="Range"\] \{ display: grid; grid-template-columns: repeat\(4, 1fr\); \}/);
  // no range is dropped on a phone: the markup still maps every range to a button
  assert.match(read("src/charts/price/PriceChart.tsx"), /RANGES\.filter\(\(r\) => offered\.includes\(r\.tf\) \|\| offered\.includes\("1d"\)\)\.map\(\(r\) => \(\n\s*<button key=\{r\.key\}/);
});

test("VR7-004: the signed-out library keeps every card in the page and a phone shows twelve, then Show 12 more", () => {
  const src = read("src/pages/PublicLibrary.tsx");
  assert.match(src, /const PHONE_CARDS = 12;/);
  assert.match(src, /shown\.map\(\(e, i\) => \(\n\s*<Card key=\{e\.id\}[^\n]*lib-lean\$\{i >= PHONE_CARDS \* cardPages \? " lib-extra" : ""\}/);   // all cards are rendered; the rest carry a class
  assert.doesNotMatch(src, /shown\.slice\(/);
  assert.match(src, /data-testid="lib-show-more"/);
  const css = read("src/pages/trade/trade.css");
  assert.match(css, /@media \(max-width: 640px\) \{ \.k-cards\.lib-cards > \.k-card\.lib-extra \{ display: none; \} \.k-row\.lib-more \{ display: flex; \} \}/);
  assert.match(css, /\.k-row\.lib-more \{ display: none; \}/);                        // a desktop has no such button
});

test("VR7-006: Key numbers are three equal columns, so a second row's figures sit under the first row's; the note on the bars fills the free cell", () => {
  const inv = read("src/styles-invest.css");
  assert.match(inv, /@media \(min-width: 1200px\) \{\n  \.inv-metrics \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); \}\n\}/);
  assert.doesNotMatch(inv, /\.inv-metrics > :last-child:nth-child\(3n\+1\) \{ grid-column: span 6; \}/);       // no widened last row
  const src = read("src/components/Research.tsx");
  assert.match(src, /className=\{`k-note inv-metrics-note\$\{groups\.length % 3 === 0 \? " row" : ""\}`\} data-testid="krail-legend"/);
  assert.match(src, /<\/p>\n\s*\)\}\n\s*<\/div>\n\s*\{foot\.length > 0 && <ul className="k-note cmp-foots" data-testid="metric-notes">.*<\/ul>\}\n\s*\{used\.length > 0/);       // (LIVE1A-062: a long note is a footnote under the grid)       // the note is the grid's last cell; the terms stay under the grid
});

test("VR7-007: on a visitor's wide page the cookie question is a slim bar along the foot of the window, in the app it stays the corner card", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(min-width: 901px\) \{\n  body:not\(:has\(\.shell\)\) \.consent \{ left: 16px; right: 16px; width: auto; flex-direction: row;/);
  assert.match(css, /\.consent \{ position: fixed; right: 16px; bottom: 16px;/);          // the corner card is still the base
});

test("VR7-008: a chart with a drawing rail is at least as tall as the rail (the Market Watch panel's 260px chart had a rail 100px taller hanging below it)", () => {
  const css = read("src/charts/price/priceChart.css");
  assert.match(css, /\.pc-main:has\(> \.pc-rail\) \{ align-items: stretch; \}/);
  assert.match(css, /\.pc-main:has\(> \.pc-rail\) > \.pc-stage \{ height: auto; min-height: var\(--pc-h, 420px\); \}/);
});

test("VR7-009: the Market Watch panel's controls are 44px targets on a phone or a touch screen", () => {
  const css = read("src/components/watch/watch.css");
  const block = css.slice(css.indexOf("VR7-009"));
  assert.match(block, /@media \(max-width: 900px\), \(pointer: coarse\) \{/);
  for (const rule of [/\.mw-ic \{ width: 44px; height: 44px; \}/, /\.mw-tab \{ min-height: 44px; \}/, /\.mw-grip \{ width: 44px; \}/, /\.mw-dots \{ width: 44px; height: 44px; \}/, /\.mw-back \{ min-height: 44px; \}/]) assert.match(block, rule);
});

test("VR7-010: on a phone the chart's reset and full-screen buttons sit after the scale buttons in the foot, not alone on a line of the toolbar", () => {
  const css = read("src/charts/price/priceChart.css");
  assert.match(css, /\.pc-foot-r \{ flex-wrap: wrap; justify-content: stretch; gap: 6px; \}\n  \.pc-foot-r \.pc-end \{ order: 2; margin-left: auto; \}/);
});

test("VR7-011: only the Market Watch list scrolls and shrinks: the list tabs do not collapse when the add-symbol form is open", () => {
  assert.match(read("src/components/watch/watch.css"), /\.mw > :not\(\.mw-scroll\):not\(\.mw-chartview\) \{ flex-shrink: 0; \}/);
});

test("VR7-012: a long usage value on Account reads from the left on a phone", () => {
  assert.match(read("src/styles.css"), /@media \(max-width: 899px\) \{ \.k-rows > div\.long > b \{ flex: 1 1 100%; text-align: left; \} \}/);
});

test("VR7-013: the first plan table fits its card at 390px and 360px", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 410px\) \{ \.k-nowrap \{ white-space: normal; \} \}/);
  assert.match(css, /@media \(max-width: 380px\) \{ \.k-compare \.k-table th, \.k-compare \.k-table td,[^}]*font-size: 13px; padding-left: 4px; padding-right: 4px; \} \}/);
});

test("VR7-014, VR7-015: the 52-week phrase is a line of its own on a phone; a holdings filing's pill takes its own line when it does not fit beside the date", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(max-width: 420px\) \{ \.nowrap\.fit \{ display: block; white-space: normal; \} \.fit-dot \{ display: none; \} \}/);
  assert.match(read("src/pages/PulseMood.tsx"), /header: "Against 52-week high"/);          // MOOD-1: a table column of its own, no longer a phrase in a tile
  assert.match(css, /@media \(max-width: 420px\) \{ \.h-filing \{ display: flex; flex-wrap: wrap;/);
});

test("VR7-019: on a laptop the Markets button is a round 44px button that fits the page's right margin; from 1600px it keeps its word", () => {
  const css = read("src/components/watch/launcher.css");
  assert.match(css, /@media \(min-width: 901px\) and \(max-width: 1599px\) \{\n  \.mw-launch\.app \{ width: 44px; min-height: 44px; padding: 0; justify-content: center; right: 6px; \}\n  \.mw-launch\.app span \{ display: none; \}/);
  assert.match(read("src/components/watch/Launcher.tsx"), /aria-label="Open Market Watch" title="Markets"/);
});
