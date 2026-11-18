// fix15 (LIVE12A, 18 Nov 2026): the scored live review of Release 69 — markets, calendars, IPOs, movers, landing. Each test reads the
// source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

test("LIVE12A-003: a sector chart served while it is brought to the latest close says so and is read again until the new one is in", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /updating\?: boolean;/);
  assert.match(s, /export const ROTATION_RECHECK_MS = 8000;/);
  assert.match(s, /if \(!out\?\.updating \|\| rechecks >= ROTATION_RECHECKS\) return;/);
  assert.match(s, /out\.updating && !out\.kept \? " · being brought to the latest close" : ""/);
});

test("LIVE12A-008: the Usual move column goes when no row has a usual move (a 'since the latest results' line alone keeps none); zero size chips are not offered", async () => {
  const { movesEmpty } = await import("../src/lib/resultsRows.ts");
  const rows = Array.from({ length: 30 }, (_, i) => ({ symbol: `S${i}` }));
  const back = Object.fromEntries(rows.map((r, i) => [r.symbol, i % 3 ? null : { moves: null, since: { date: "2026-11-17", pct: -0.4 } }]));
  assert.equal(movesEmpty(rows, back), true);
  assert.equal(movesEmpty(rows, { ...back, S1: { moves: { avg: 3, last: [1] } } }), false);
  const f = read("src/components/CalendarFilters.tsx");
  assert.match(f, /export const sizeChoices = \(sizes: Facets\["sizes"\], picked: string\[\], narrowed = false\) => sizes\.filter\(\(s\) => narrowed \|\| s\.count > 0 \|\| picked\.includes\(s\.id\)\);/);
  assert.match(f, /options=\{sizeChoices\(facets\.sizes, filters\.size, active > 0\)\.map/);
});

test("LIVE12A-005: Movers on a phone: the Stocks field is drawn while the lists load, the loading card holds the list's place, the CSV is in the card's head, and a symbol never runs into its name", () => {
  const s = read("src/pages/MoversPage.tsx");
  assert.match(s, /\{\(!view \|\| view\.universes\.length > 0\) && \(/);
  assert.match(s, /<Select id=\{id\} value="" disabled onChange=\{\(\) => undefined\} options=\{\[\{ value: "", label: "Reading…" \}\]\} \/>/);
  assert.match(s, /<Card className="mv-wait"><Working label="Reading the market's closes" \/><\/Card>/);
  assert.match(read("src/pages/movers.css"), /\.mv-wait \{ min-height: 520px; \}/);
  assert.match(s, /actions=\{!locked && rows\.length > 0 \? <CsvButton name=\{`movers \$\{name\} \$\{meta\.label\}`\}/);
  assert.doesNotMatch(s, /<DataTable csv=/);
  assert.match(read("src/styles.css"), /\.k-table td a, \.k-table th a, \.k-cal-ev a \{ column-gap: 0\.3em; \}/);
});

test("LIVE12A-011: Breadth's live card has its CSV in the card's head beside the Live tag, never alone on a row", () => {
  const s = read("src/pages/BreadthPage.tsx");
  assert.match(s, /data-testid="breadth-live-tools"/);
  assert.match(s, /\{rows\.length > 0 && <CsvButton name="breadth today" label=\{liveLabel\} columns=\{cols\} rows=\{rows\} \/>\}/);
  assert.doesNotMatch(s, /<DataTable csv="breadth today"/);
});

test("LIVE12A-011: the one coloured breadth share says its colour rule in its row", async () => {
  const { measureRows, HALF_MEANS } = await import("../src/lib/breadthTable.ts");
  assert.equal(HALF_MEANS, "Share of stocks priced above their 50-day average; green above half, red below.");
  const fig = (value) => ({ value, prev: value, change: 0 });
  const t = { day: "2026-11-16", prev_day: "2026-11-13", adv: fig(300), dec: fig(200), unch: fig(5), stocks: fig(505), pct20: fig(40), pct50: fig(61), pct200: fig(30),
    highs: fig(10), lows: fig(4), up4: fig(3), down4: fig(2), ad_ratio: fig(1.5), mcclellan: fig(10), summation: fig(100), trin: fig(1), stage2: fig(20) };
  assert.equal(measureRows(t, null).find((r) => r.key === "p50").means, HALF_MEANS);
});

test("LIVE12A-010: a mid-size heatmap tile (about 57 × 53 px) names a long symbol over two lines; the facts line counts the tiles on the map", async () => {
  const { tileWords } = await import("../src/lib/heatmap.ts");
  const width = (text) => text.length * 6.5;
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 57, 53, width), { px: 10, fig: false, split: 5 });
  assert.deepEqual(tileWords("BAJAJ-AUTO", "+1.2%", 46, 50, width), { px: 9, fig: false, split: 6 });       // split after the hyphen
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 60, 40, width), { px: 0, fig: false });                   // one line's height: none
  assert.match(read("src/components/chart/Treemap.tsx"), /\{split \? <>\{p\.tile\.s\.slice\(0, split\)\}<wbr \/>\{p\.tile\.s\.slice\(split\)\}<\/> : p\.tile\.s\}/);
  assert.match(read("src/components/chart/treemap.css"), /\.hm-sym\.two \{ white-space: normal; width: min-content;/);
  const h = read("src/pages/HeatmapPage.tsx");
  assert.match(h, /data-testid="hm-count"/);
  assert.match(h, /onMap\.toLocaleString\("en-IN"\)\}<\/b> of \{tiles\.length\.toLocaleString\("en-IN"\)\} companies on the map/);
});

test("LIVE12A-007: a layer whose companies are all in the theme the same way says it once; the column wraps; the own-words column keeps its width", () => {
  const s = read("src/components/ThemeDive.tsx");
  assert.match(s, /\{ key: "f", header: "In the theme by", wrap: true, cell:/);
  assert.match(s, /const same = !sameBy && g\.rows\.length > 1 && new Set\(g\.rows\.map\(byOf\)\)\.size === 1;/);
  assert.match(s, /cols=\{same \? cols\.filter\(\(c\) => c\.key !== "f"\) : cols\}/);
  assert.match(s, /data-testid="layer-by-once">Every company in this layer is in the theme by: \{byOnce\}\./);
  assert.match(read("src/styles.css"), /@media \(min-width: 901px\) \{ #theme-members \.k-table td\.k-lead \{ min-width: 18rem; \} \}/);
});

test("LIVE12A-013: a visitor's page code and the visitor half are asked for beside the two start-up helpers, not after them", () => {
  const e = read("src/entry.tsx");
  const helpers = e.indexOf('await Promise.all([import("./lib/share"), import("./lib/sentry")])');
  assert.ok(helpers > 0);
  assert.ok(e.indexOf("const early = account ? null : publicPage(path)") < helpers, "the page's code first");
  assert.ok(e.indexOf('const visitorCode = account ? null : import("./visitor/visitorMain")') < helpers, "the visitor half first");
  assert.match(e, /const visitor = await visitorCode!;/);
});

test("LIVE12A-002: a signed-in app's first load doesn't download the error reporter beside its own code: it comes after the page has drawn", () => {
  const s = read("src/lib/sentry.ts");
  assert.match(s, /const SENTRY_AFTER_MS = 4000;/);
  assert.doesNotMatch(s, /if \(!lazy\) \{ void load\(\); return; \}/);
  assert.match(s, /const go = \(\) => setTimeout\(first, SENTRY_AFTER_MS\);/);
  assert.match(s, /if \(!lazy\) \{ if \(document\.readyState == "complete"\) go\(\); else addEventListener\("load", go, \{ once: true \}\); \}/);
  assert.match(s, /removeEventListener\("error", onError\);/);             // once loaded, the early listeners stop: nothing twice
});

test("LIVE12A-013/002: the bundler's preload helper rides in the start-up file, so the entry never waits for React before asking for a page's code", () => {
  assert.match(read("vite.config.ts"), /\{ name: "boot", priority: 1, test: \/src\[\\\\\/\]lib\[\\\\\/\]\(entry\|config\|http\|returnTo\)\\\.ts\$\|vite\[\\\\\/\]preload-helper\/ \},/);
});
