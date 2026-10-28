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
  assert.match(src, /<\/p>\n\s*\)\}\n\s*<\/div>\n\s*\{used\.length > 0/);       // the note is the grid's last cell; the terms stay under the grid
});

test("VR7-007: on a visitor's wide page the cookie question is a slim bar along the foot of the window, in the app it stays the corner card", () => {
  const css = read("src/styles.css");
  assert.match(css, /@media \(min-width: 901px\) \{\n  body:not\(:has\(\.shell\)\) \.consent \{ left: 16px; right: 16px; width: auto; flex-direction: row;/);
  assert.match(css, /\.consent \{ position: fixed; right: 16px; bottom: 16px;/);          // the corner card is still the base
});
