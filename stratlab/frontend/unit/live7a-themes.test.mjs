// LIVE7A (the live review of Release 41's theme pages), lane t1: the page reads the same records and rules as the deck.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE7A-004: an encyclopedia lead, an 'also' line or a 'where' line is not a company's own words (theme_base.own_words)", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  const cases = [
    ["Toyo Tire Corporation, commonly known as Toyo Tires, is a multinational tire and rubber products company based in Itami, Japan", "TOYO Co., Ltd", false],
    ["Monolithic Power Systems, Inc. is an American, publicly traded company headquartered in West Palm Beach, Florida", "Monolithic Power Systems Inc", false],
    ["SK hynix Inc. is a South Korean supplier of DRAM and flash memory chips", "SK Hynix", false],
    ["We also offer data center rack-scale platform designs", "Advanced Micro Devices", false],
    ["It is headquartered in Little Rock, Arkansas, and operates 270 stores", "Dillards Inc", false],
    ["We design, manufacture, test and market analog and mixed-signal chips", "Analog Devices", true],
    ["The Company is an India-based manufacturer of two-wheelers", "Two Wheels Ltd", true],
    ["Motherson Sumi Systems is engaged primarily in the manufacture and sale of components to automotive makers", "Samvardhana Motherson", true],
  ];
  for (const [t, n, shown] of cases) assert.equal(!!TF.ownWords(t, n), shown, t);
  // the backend's cases are the same list (tests/test_live7a_themes.py OWN_CASES_7A)
  const py = readFileSync(new URL("../../backend/tests/test_live7a_themes.py", import.meta.url), "utf8");
  for (const [t] of cases) assert.ok(py.includes(JSON.stringify(t)), t);
});

test("LIVE7A-009: an EBITDA margin filed in whole points prints whole on the page, as on the deck", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  assert.equal(TF.pcw(12, true), "12%");
  assert.equal(TF.pcw(16.5, true), "16.5%");
  assert.equal(TF.pcw(12, false), "12.0%");
  assert.equal(TF.pcw(-3, true), "−3%");
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /pcw\(x\.row!\[k\], x\.row!\.ebitda_dp === 0\)/);
  assert.match(src, /layerColumns\(region, wide, layer\.left_out > 0, !!layer\.ebitda_whole\)/);
});

test("LIVE7A-008: the theme list says the day the theme's page says (the map's own day, in the market's time zone)", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  const fmt = (d) => d;
  assert.equal(TF.libraryLabel({ name: "Automotive", region: "IN", at: "2026-11-07T21:30:00+00:00", day: "2026-11-08" }, fmt), "Automotive · India, updated 2026-11-08");
  assert.equal(TF.libraryLabel({ name: "Chips", region: "US", at: "2026-11-07T21:30:00+00:00" }, fmt), "Chips · US, updated 2026-11-07");
});

test("LIVE7A-005: a layer's operating figures are its own companies', whatever the map's order of layers", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  const biz = { layers: [{ layer: "Two-wheelers", rows: [{ symbol: "HERO" }, { symbol: "TVS" }] }, { layer: "Trucks", rows: [{ symbol: "ASHOK" }] }] };
  // the page's layers are not the map's: an extra layer before them put each table one layer low
  assert.deepEqual(TF.bizFor(biz, { companies: [{ symbol: "TVS" }, { symbol: "HERO" }, { symbol: "NONE" }] }), [{ symbol: "TVS" }, { symbol: "HERO" }]);
  assert.deepEqual(TF.bizFor(biz, { companies: [{ symbol: "ASHOK" }] }), [{ symbol: "ASHOK" }]);
  assert.equal(TF.bizFor(null, { companies: [] }), undefined);
  assert.match(read("src/pages/ThemesPage.tsx"), /business=\{bizFor\(biz, l\)\}/);
});

test("LIVE7A-011: a layer's table lists the largest company first", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  const row = (symbol, cap) => ({ symbol, name: symbol, cap, net: 1, ebitda: 1, roce: null, revenue: 10, calc: { in: true, why: "" } });
  const layer = { layer: "L", companies: [row("SANSERA", 25936), row("CRAFTSMAN", 27389), row("NOCAP", null), row("BALKRISHNA", 46589)], n: 4, stats: { ebitda: null, net: null, roce: null }, stats_over: "own" };
  assert.deepEqual(TF.layerLines(layer).filter((x) => x.kind === "company").map((x) => x.key), ["BALKRISHNA", "CRAFTSMAN", "SANSERA", "NOCAP"]);
});

test("LIVE7A-013, 002, 003, 007: the page's words and reads", () => {
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /<Badge tone="ok" dot=\{false\}>Dated source<\/Badge>/);
  assert.ok(!/>Checked</.test(dive) && dive.includes("it is not a check of the claim"));
  assert.match(dive, /header: "Average company"/);
  assert.match(dive, /prices\.missing \?\? prices\.pending/);
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /prices to the \$\{fmtDate\(dive\.as_of\)\} close/);
  assert.match(page, /as_of_older/);
  assert.match(page, /if \(l\.pending && \+\+ipoTries < LISTING_TRIES\) ipoTimer = setTimeout\(listings, PRICE_EVERY_MS\)/);
});

test("LIVE7A-011: an SEC industry title is worded for a reader; an Indian industry's name is left as it is", async () => {
  const TF = await import("../src/lib/themeFormat.ts");
  assert.equal(TF.plainIndustry("Radio & Tv Broadcasting & Communications Equipment"), "Radio and TV broadcasting and communications equipment");
  assert.equal(TF.plainIndustry("Special Industry Machinery, Nec"), "Special industry machinery");
  assert.equal(TF.plainIndustry("Services-Prepackaged Software"), "Prepackaged software");
  assert.equal(TF.plainIndustry("Auto Components & Equipments"), "Auto components and equipments");
  assert.equal(TF.plainIndustry("2/3 Wheelers"), "2/3 wheelers");
  assert.equal(TF.plainIndustry("Passenger Cars & Utility Vehicles"), "Passenger cars and utility vehicles");
  assert.equal(TF.plainIndustry(null), "");
  // on the page, for a US theme only: an Indian theme's industries are said as the exchange lists them, as in its "Official industries" line
  assert.match(read("src/components/ThemeDive.tsx"), /region === "US" \? plainIndustry\(c\.industry\) : c\.industry/);
});
