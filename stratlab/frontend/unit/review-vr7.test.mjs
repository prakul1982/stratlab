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
