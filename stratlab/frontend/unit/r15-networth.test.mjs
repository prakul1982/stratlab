// R15 #3 (owner, 7 Nov: "tf is this ui it was fine before"): Net worth's "Where you stand" totals are a full-width row again, the
// figures right-aligned, as before R14's compact half-width block (71a6d16). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R15 #3: the totals across one row fill the card, figures right-aligned", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-facts-across \.k-table \{ table-layout: fixed; width: 100%; \}/);
  assert.doesNotMatch(css, /\.k-facts-across \.k-tbl-wrap \{ display: inline-block/, "the compact half-width block is back");
  assert.match(css, /\.k-facts-across \.k-facts-cell \{[^}]*align-items: flex-end/);
  const ft = read("src/components/kit/FactTable.tsx");
  assert.match(ft, /csvHeader: typeof r\.k === "string" \? r\.k : r\.id, numeric,/, "the across columns are numeric (right-aligned)");
});
