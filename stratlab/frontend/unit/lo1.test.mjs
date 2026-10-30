// LO-1: the last leftovers before the weekly reset (30 Oct 2026). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LO1-1: on a phone undo, redo and the shortcuts (i) move from the chart's top bar into the Draw sheet", () => {
  const chart = read("src/charts/price/PriceChart.tsx");
  assert.match(chart, /\{!phone && <span className="pc-endtools"><HistoryButtons /);
  const sheet = read("src/charts/price/DrawToolbar.tsx");
  assert.match(sheet, /<div className="pc-sheet-more"><HistoryButtons \{\.\.\.p\} \/><ShortcutsButton \/><\/div>/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-sheet-more \{ display: flex;/);
});
