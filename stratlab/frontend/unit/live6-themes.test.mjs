// LIVE6 (the live review of Release 34): the theme page reads the same records as the deck.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const row = (symbol, net, calc) => ({ symbol, name: symbol, net, ebitda: net, roce: null, revenue: 10, calc });

test("LIVE6-001: a layer's median is of the companies in its calculations, never under 3, and a left-out row says why", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  // the live Cybersecurity layer 1: 2.7% and 38.8% listed, one of them left out; the page printed "Median of 2 companies 2.7%"
  const layer = { layer: "L1", companies: [row("A", 2.7, { in: true, why: "" }), row("B", 38.8, { in: false, why: "other business" })],
    n: 1, listed: 2, stats: { ebitda: { n: 1, median: 2.7, min: 2.7, max: 2.7 }, net: { n: 1, median: 2.7, min: 2.7, max: 2.7 }, roce: null }, stats_over: "own" };
  const lines = TF.layerLines(layer);
  assert.deepEqual(lines.map((x) => x.kind), ["company", "company", "median"]);          // no range under a median that isn't shown
  assert.equal(lines[2].label, "Median of the 1 in the layer's calculations");
  assert.deepEqual(TF.medCell(layer.stats.net, 1), { text: "–", base: "1" });
  assert.deepEqual(TF.medCell({ n: 2, median: -0.1, min: -0.8, max: 0.5 }, 3), { text: "–", base: "2 of 3" });
  assert.deepEqual(TF.medCell({ n: 4, median: 8.1, min: 1, max: 9 }, 5), { text: "8.1%", base: "4 of 5" });
  assert.deepEqual(TF.medCell({ n: 5, median: 8.1, min: 1, max: 9 }, 5), { text: "8.1%", base: "" });
  assert.equal(TF.calcOf(layer.companies[1]).in, false);
  assert.equal(TF.CALC_WORDS["other business"], "it earns another way than most of this layer's companies");
  // the page marks the row and the chain's count is "N of M"
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /Left out of the layer's calculations: \{CALC_WORDS\[c\.why\]/);
  assert.match(src, /x\.listed && x\.listed > x\.n \? `\$\{x\.n\} of \$\{x\.listed\}`/);
});

test("LIVE6-002: the price table says the close its periods run to, and the chart's axis is by date (with years)", () => {
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /Over, to \$\{fmtDate\(prices\.returns_to\)\}/);
  assert.match(src, /times=\{prices\.line\.weeks\}/);
});
