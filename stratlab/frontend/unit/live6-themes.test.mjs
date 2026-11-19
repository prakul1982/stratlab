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
  // (updated on purpose, ex49: the server's precise reason where it keeps one, theme_data.out_reason; CALC_WORDS for a record kept before)
  assert.match(src, /Left out of the layer's calculations: \{calcWords\(c\)\}/);
  assert.equal(TF.calcWords({ why: "other business" }), "it earns another way than most of this layer's companies");
  assert.equal(TF.calcWords({ why: "other business", kind: "different revenue model",
    detail: "the way of earning of “Platforms and marketplaces” (commissions), not the layer's, that of “Retail” (the margin on goods)" }),
  "different revenue model: the way of earning of “Platforms and marketplaces” (commissions), not the layer's, that of “Retail” (the margin on goods)");
  assert.match(src, /x\.listed && x\.listed > x\.n \? `\$\{x\.n\} of \$\{x\.listed\}`/);
});

test("LIVE6-002: the price table says the close its periods run to, and the chart's axis is by date (with years)", () => {
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /Over, to \$\{fmtDate\(prices\.returns_to\)\}/);
  assert.match(src, /times=\{prices\.line\.weeks\}/);
});

test("LIVE6-007: the page shows a line as a company's own words by the deck's rule (theme_base.own_words)", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  const cases = [
    ["From its own filings: Annual report (20-F).", "Check Point Software", false],
    ["Annual report (20-F)", "Check Point Software", false],
    ["Fortinet, Inc.", "Fortinet, Inc.", false],
    ["Fortinet, Inc. is an American multinational corporation headquartered in Sunnyvale, California", "Fortinet, Inc.", false],
    ["Rapid7 is an American cybersecurity company headquartered in Boston, Massachusetts", "Rapid7, Inc.", false],
    ["Fortinet provides cybersecurity solutions to enterprises and service providers", "Fortinet, Inc.", true],
    ["Tata Motors Limited is a leading global automobile manufacturer", "Tata Motors Ltd", true],
    ["The company is engaged in the business of manufacturing auto components", "Uno Minda Ltd", true],
    ["It manufactures steel wheels for cars", "Steel Strips Wheels Ltd", true],
  ];
  for (const [t, n, shown] of cases) assert.equal(!!TF.ownWords(t, n), shown, t);
  assert.equal(TF.NO_WORDS, "No description in its own words yet");
  // the backend's cases are the same list (tests/test_live6_themes.py OWN_CASES)
  const py = readFileSync(new URL("../../backend/tests/test_live6_themes.py", import.meta.url), "utf8");
  for (const [t] of cases) assert.ok(py.includes(JSON.stringify(t)), t);
});

test("LIVE6-006: one market value per company on the page: the dive's wherever it has the company", () => {
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /amount\(caps\.get\(c\.ticker\) \?\? c\.cap \?\? null, region\)/);
  // (updated on purpose, Release 43) the companies CSV is made by the server from the same rows: the dive's market value where it has one
  assert.match(read("../backend/app/intel/theme_routes.py"), /"cap": f\.get\("cap"\) if f\.get\("cap"\) is not None else c\.get\("cap"\)/);
  assert.match(read("src/pages/ThemesPage.tsx"), /<MembersCard r=\{r\} region=\{region\} dive=\{dive\} \/>/);
});

test("LIVE6-017: section links at the top, long tables folded, tables titled, all-dash rows dropped, no promoters on a US theme", () => {
  const page = read("src/pages/ThemesPage.tsx");
  // the links come before the companies' card, not after it
  assert.ok(page.indexOf("<PageNav items={nav} />") < page.indexOf("<MembersCard"), "nav before the members");
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /function Fold<T>/);
  for (const what of ["Every company in the theme with its figures", "Latest dated headlines and filings for the theme", "The theme's median P/E over time"])
    assert.ok(new RegExp(`<Fold[^\\n]*\\n?[^\\n]*label="${what.replace(/[()]/g, "\\$&")}"`).test(src) || src.includes(`<DataTable label="${what}" columns={cols} rows={shown}`) || src.includes(`(shown) => <DataTable label="${what}"`), what);
  assert.match(src, /<h3 className="k-sub">The theme's median P\/E, week by week<\/h3>/);
  assert.match(src, /Margins by year, the same \{hist\.n\} companies added together/);
  assert.match(src, /rows=\{said\(rows\)\}/);
  assert.match(src, /\{r === "IN" && <>\s*\n\s*<h3 className="k-sub">Promoter and named institutional holdings<\/h3>/);
  assert.match(src, /const basisWords = \(b: string\) => b\.replace\(/);
});
