// THEME-1 (29 Oct 2026): the theme deep dive. Figures are tables with aligned columns; the page reads no figure from the AI.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("the theme figures are written the app's way: Indian money, one-decimal percents, the real minus", async () => {
  const { amount, pc, times, points, span } = await import("../src/lib/themeFormat.ts");
  assert.match(amount(1500, "IN"), /^₹.*cr$/);
  assert.equal(amount(null, "IN"), "–");
  assert.equal(pc(49), "49.0%");
  assert.equal(pc(-3.25), "−3.3%");
  assert.equal(pc(null), "–");
  assert.equal(times(12.34), "12.3x");
  assert.equal(points(2), "+2.0 pts");
  assert.equal(points(-0.5), "−0.5 pts");
  assert.equal(span({ n: 2, median: 49, min: 48, max: 50 }), "48.0% to 50.0%");
  assert.equal(span({ n: 1, median: 49, min: 49, max: 49 }), "49.0%");
  assert.equal(span(null), "–");
});

test("a layer's table is its companies, then the median and the range as rows; a layer with no company has no table", async () => {
  const { layerLines } = await import("../src/lib/themeFormat.ts");
  const layer = (companies, over = "own") => ({ layer: "L", companies, stats: { ebitda: null, net: null, roce: null }, stats_over: over });
  const lines = layerLines(layer([{ symbol: "A" }, { symbol: "B" }]));
  assert.deepEqual(lines.map((l) => l.kind), ["company", "company", "median", "range"]);
  assert.equal(lines[2].label, "Median");
  assert.equal(layerLines(layer([{ symbol: "A" }], "all"))[1].label, "Median (all company-wide)");
  assert.deepEqual(layerLines(layer([])), []);
});

test("the page is made of tables: no stat tiles, no chips, the kit's DataTable, and the company links go to the company page", () => {
  for (const f of ["src/pages/ThemesPage.tsx", "src/components/ThemeDive.tsx"]) {
    const src = read(f);
    assert.doesNotMatch(src, /<Stat\b|<StatRow\b|inv-chip|inv-chain|k-stat/, f);
    assert.doesNotMatch(src, /toFixed\(1\)\}%|style=\{\{/, f);                 // percents through lib/format, no inline styles
  }
  const dive = read("src/components/ThemeDive.tsx");
  assert.ok((dive.match(/<DataTable/g) ?? []).length >= 20);
  assert.match(dive, /\/research\/\$\{r\}\/\$\{encodeURIComponent\(sym\)\}/);
  assert.match(dive, /In its own words/);
});

test("the page names no data provider and gives no advice", () => {
  for (const f of ["src/pages/ThemesPage.tsx", "src/components/ThemeDive.tsx", "src/lib/theme.ts", "src/lib/themeFormat.ts"]) {
    const src = read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    assert.doesNotMatch(src, /yahoo|screener\.in|finnhub|trendlyne|zerodha/i, f);
    assert.doesNotMatch(src, /\b(buy|sell|accumulate|undervalued|overvalued)\b/i, f);
  }
});

test("Research.tsx hands the Themes page to its own file, and the sector read still goes through the research API", () => {
  assert.match(read("src/pages/Research.tsx"), /export \{ ThemesPage \} from "\.\/ThemesPage"/);
  assert.match(read("src/lib/research.ts"), /\/research\/sector\?region=/);
  assert.match(read("src/lib/theme.ts"), /\/research\/theme-dive\?/);
});
