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
  const layer = (companies, over = "own") => ({ layer: "L", companies, stats: { ebitda: { n: companies.length, median: 1, min: 1, max: 2 }, net: null, roce: null }, stats_over: over });
  const lines = layerLines(layer([{ symbol: "A" }, { symbol: "B" }]));
  assert.deepEqual(lines.map((l) => l.kind), ["company", "company", "median", "range"]);
  assert.equal(lines[2].label, "Median of 2 companies");
  assert.equal(layerLines(layer([{ symbol: "A" }], "all"))[1].label, "Median of 1 company (company-wide figures)");
  assert.deepEqual(layerLines(layer([])), []);
  assert.deepEqual(layerLines(layer([{ symbol: "A" }])).map((l) => l.kind), ["company", "median"]);        // one company: no range
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

test("THEMES: every company of the theme's official industries is listed by layer, the AI's additions marked, the counts said once", () => {
  const dive = read("src/components/ThemeDive.tsx"), page = read("src/pages/ThemesPage.tsx");
  assert.match(dive, /export function MembersCard/);
  for (const h of ["Company", "Industry", "Market value", "What it does, in its own words", "In the theme by"]) assert.match(dive, new RegExp(`header: "${h}"`));
  assert.match(dive, /from the official industry list, \{named > 0 && `\$\{named\.toLocaleString\("en-IN"\)\} named in the theme's list, `\}\{added\.toLocaleString\("en-IN"\)\} added/);
  assert.match(dive, /Not yet confirmed from its own description/);
  assert.match(dive, /c\.base \? \(c\.basis === "list" \? "Named in the theme's list" : "Official industry"\)/);
  assert.match(dive, /named in the theme's list, /);
  assert.match(dive, /matched by the theme's own words/);                       // the page says which industries a typed theme used, and how
  assert.match(dive, /US-listed companies have no industry on file yet/);
  assert.match(dive, /Show all \$\{rows\.length\} companies/);                       // a long group is listed in full a press away, never "and N more"
  // a check still waiting is asked again on its own, and once the server stops waiting the page says so plainly, with no warning box
  assert.match(page, /const CHECK_TRIES = 18;/);                                  // 18 x 5 s: the 90 s give-up (LIVE3-001)
  assert.match(page, /r\?\.ai\?\.state === "working"/);
  // work still running is the shared moving bar with one short line (owner, 5 Nov: "a nice animated loading bar, don't show exact warnings");
  // a company whose check timed out keeps its "not yet confirmed" mark, without a note about the timeout
  assert.match(page, /\{pending && \(\n\s+<Working label=/);
  assert.doesNotMatch(page, /pl\?\.timed_out|tone="warn" action=\{\{ label: "Check again"/);
  assert.doesNotMatch(page, /On the exchange's list for these industries/);
});

test("tailwinds and risks say 'no dated source' once under the table, not under every row (LIVE3-017)", () => {
  const dive = readFileSync(new URL("../src/components/ThemeDive.tsx", import.meta.url), "utf8");
  const card = dive.slice(dive.indexOf("export function ClaimsCard"), dive.indexOf("export function NewsCard"));
  assert.doesNotMatch(card, /k-sub-line">No dated source/);
  assert.equal((card.match(/no dated headline was found/g) || []).length, 1);
  assert.match(card, /rows\.some\(\(x\) => !\(x\.status === "current" && x\.source\)\) && <p className="k-note">General background:/);
});
