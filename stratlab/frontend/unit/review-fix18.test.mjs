// Lane fix18: the LIVE13A review's market, calendar, panel and phone findings.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE13A-012/-029: the heatmap and movers say live prices, the day's last trades, or that the latest closes are being added", async () => {
  const { dayLine } = await import("../src/lib/heatmap.ts");
  const d = (iso) => ({ "2026-11-17": "17 Nov 2026", "2026-11-18": "18 Nov 2026" })[iso];
  const live = dayLine({ as_of: "2026-11-17", live: { day: "2026-11-18", time: "14:00", close: false } }, true, "map", d, "IST");
  assert.equal(`${live.lead}${live.day}${live.tail}`, "Prices at 14:00 IST, 18 Nov 2026 · the market is open; the map is redrawn every 15 minutes");
  assert.equal(live.price, "Last price");
  const lists = dayLine({ as_of: "2026-11-17", live: { day: "2026-11-18", time: "14:00", close: false } }, true, "lists", d, "IST");
  assert.match(lists.tail, /the lists are redrawn every 15 minutes$/);
  const bell = dayLine({ as_of: "2026-11-17", live: { day: "2026-11-18", time: "15:30", close: true } }, false, "map", d, "IST");
  assert.equal(`${bell.lead}${bell.day}${bell.tail}`, "Last trades of 18 Nov 2026 · the official closes replace them after the evening run");
  // 16:05 IST on 18 Nov with no prices of it: no longer a bare "Closes of 17 Nov"
  const behind = dayLine({ as_of: "2026-11-17", behind: true }, false, "map", d, "IST");
  assert.equal(`${behind.lead}${behind.day}${behind.tail}`, "Closes of 17 Nov 2026 · the latest session's closes are being added");
  assert.equal(dayLine({ as_of: "2026-11-17" }, false, "map", d, "IST").tail, "");
  assert.equal(dayLine({ as_of: null }, false, "map", d, "IST"), null);
  for (const page of ["src/pages/HeatmapPage.tsx", "src/pages/MoversPage.tsx"]) assert.match(read(page), /\{line\.lead\}<b>\{line\.day\}<\/b>\{line\.tail\}/);
});

test("LIVE13A-012: a 40-46 px heatmap tile names its symbol (over two lines when one doesn't fit)", async () => {
  const { tileWords } = await import("../src/lib/heatmap.ts");
  const width = (text) => text.length * 6.5;
  // the review's blank tiles: about 45 × 45 px boxes, so 43 × 43 px tiles
  assert.deepEqual(tileWords("BHARATFORG", "+1.2%", 43, 43, width), { px: 10, fig: false, split: 5 });
  assert.deepEqual(tileWords("SIEMENS", "+1.2%", 43, 43, width), { px: 10, fig: false, split: 4 });
  assert.deepEqual(tileWords("ABB", "+1.2%", 43, 43, width), { px: 10, fig: true });
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 60, 28, width), { px: 0, fig: false });       // under two lines' height: none
});

test("LIVE13A-006: the Markets panel never opens on a price read hours earlier in the same session", async () => {
  const { keptQuotes, keepQuotes, SESSION_KEEP_MS } = await import("../src/lib/watchQuotes.ts");
  const mem = new Map();
  const store = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, v) };
  const now = Date.parse("2026-11-18T09:02:00Z");                                   // 14:32 IST, NSE open
  const q = (price, at) => ({ price, change: -2.65, change_pct: -0.9, prev_close: 293.3, at, currency: "INR", stale: false });
  keepQuotes("u", { "IN:ITC": q(290.65, "2026-11-18T09:58:00+05:30"), "IN:TCS": q(2393.8, "2026-11-18T14:25:00+05:30"),
    "US:AAPL": q(351.91, "2026-11-17T16:00:00-05:00") }, now - 60_000, store);
  const open = (k) => k.startsWith("IN:");
  const got = keptQuotes("u", now, store, undefined, undefined, open);
  assert.deepEqual(Object.keys(got).sort(), ["IN:TCS", "US:AAPL"]);                // 4 h 34 min old in the session: left out; a shut market's last close stays
  assert.equal(SESSION_KEEP_MS, 15 * 60 * 1000);
  assert.equal(Object.keys(keptQuotes("u", now, store)).length, 3);                 // without the market's state, as before
  assert.match(read("src/components/watch/WatchPanel.tsx"), /\(k\) => \{ const m = markets\.find\(\(x\) => x\.id === k\.split\(":"\)\[0\]\); return !!m && marketState\(m\)\.open; \}\)\);/);
});

test("LIVE13A-007: Mood's companies in the headlines are one row each", async () => {
  const { companyRows } = await import("../src/lib/pulseMood.ts");
  const rows = companyRows([{ name: "Tata Consultancy Services", ticker: "TCS" }, { name: "Titan Company", ticker: "TITAN" },
    { name: "Tata Consultancy Services (IT sector)", ticker: "TCS" }, { name: "Titan Company (consumer durables)", ticker: "" }, { name: "Indian IT stocks", ticker: "INFY" }]);
  assert.deepEqual(rows.map((r) => r.name), ["Tata Consultancy Services", "Titan Company"]);
});

test("LIVE13A-005: Results' Usual move column needs three rows with a move; a US meeting is said one way; the sort box spans two columns", async () => {
  const { movesEmpty, purposeShown, MIN_MOVES } = await import("../src/lib/resultsRows.ts");
  const rows = Array.from({ length: 408 }, (_, i) => ({ symbol: `S${i}` }));
  const back = Object.fromEntries(rows.map((r) => [r.symbol, null]));
  assert.equal(MIN_MOVES, 3);
  assert.equal(movesEmpty(rows, { ...back, S7: { moves: { avg: 16.7, last: [1] } } }), true);          // one value in 408 rows: no column
  assert.equal(movesEmpty(rows, { ...back, S1: { moves: { avg: 1 } }, S2: { moves: { avg: 2 } }, S3: { moves: { avg: 3 } } }), false);
  assert.equal(movesEmpty([{ symbol: "A" }, { symbol: "B" }], { A: { moves: { avg: 2 } }, B: null }), false);   // one of two: half of them
  assert.equal(purposeShown("US", "Quarterly results (fiscal Q3 2027)"), "Quarterly results");
  assert.equal(purposeShown("US", "Quarterly results (quarter ended Oct 2026)"), "Quarterly results");
  assert.equal(purposeShown("IN", "Financial results (quarter ended Sep 2026)"), "Financial results (quarter ended Sep 2026)");
  assert.match(read("src/components/CalendarFilters.tsx"), /<div className="res-sort">\s*<Field label="Sort by">/);
  assert.match(read("src/styles-invest.css"), /@media \(min-width: 900px\) \{ \.res-filter-grid > \.res-sort \{ grid-column: span 2;/);
});

test("LIVE13A-015: Mood's Coming up says the price band in rupees (or dollars)", () => {
  assert.match(read("src/pages/PulseMood.tsx"), /Price band \{region === "US" \? "\$" : "₹"\}\{i\.low\}–\{i\.high\}/);
  assert.match(read("src/pages/Research.tsx"), /<CalendarTable c=\{mood\.calendar\} today=\{dayIn\(new Date\(\), marketTz\(region\)\)\} region=\{region\} \/>/);
});

test("LIVE13A-030: Mood's breadth table and note say the count at the closing prices apart from the 15:30 round", () => {
  const m = read("src/pages/PulseMood.tsx");
  assert.match(m, /b\.live && b\.at_close \? ", in the count at the closing prices" : b\.live && b\.at \? `, in the \$\{b\.at\} IST count\$\{open \? "" : ", before the closing prices"\}`/);
  assert.match(m, /header: b\.live \? \(b\.at_close \? "Today, at the close" :/);
});

test("LIVE13A-018: /login's two buttons one height, a plain sentence, the company directories two to a row, no lone eyebrow word", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.lp-hero-login \.lp-hero-copy:has\(\.email-slot, \.email-signin\) \.lp-cta \{ min-height: 44px; \}/);
  assert.match(css, /\.email-signin-row \.btn \{ min-height: 44px; \}/);
  assert.match(css, /\.legal-links\[aria-label="Browse companies"\] \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  assert.match(css, /\.eyebrow \{[^}]*text-wrap: balance; \}/);
  for (const p of ["src/pages/Login.tsx", "src/pages/Gate.tsx"]) {
    assert.match(read(p), /Google sign-in reads only your name and email address\{/);
    assert.doesNotMatch(read(p), /Signing in only reads/);
  }
});

test("LIVE13A-027: earnings calls show one link per document, say a missing zone, and keep the CSV in a head", async () => {
  const src = read("src/pages/EarningsCallsPage.tsx");
  assert.match(src, /export const oneEach = <L extends \{ label: string \}>\(links: L\[\]\): L\[\] => links\.filter\(\(x, i\) => links\.findIndex\(\(y\) => y\.label === x\.label\) === i\);/);
  assert.match(src, /\{oneEach\(r\.links\)\.map\(/);
  assert.match(src, /if \(r\.time\) return `\$\{r\.time\}\$\{r\.tz \? ` \$\{r\.tz\}` : ", zone not given"\}`;/);
  assert.match(src, /<CardHead title=\{when === "past" \? "Held" : "Coming up"\} actions=\{data\.rows\.length \? <CsvButton name="earnings calls"/);
  assert.doesNotMatch(src, /<DataTable csv="earnings calls"/);
});

test("LIVE13A-020: a theme's central point follows a colon, so its own capital reads right", () => {
  assert.match(read("src/pages/ThemesPage.tsx"), /The point everything converges on: <b>\{r\.core\}<\/b>\./);
  assert.doesNotMatch(read("src/pages/ThemesPage.tsx"), /Everything converges on <b>/);
});

test("LIVE13A-019: on a phone a wrapped card title keeps its (i) after its last word, a lone CSV stays on the title's line, Movers' lists are rows of two", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-card-titlerow \{ display: block; \}\n  \.k-card-titlerow > \.k-card-title \{ display: inline; \}/);
  assert.match(css, /\.k-card-head:has\(> \.k-card-actions > \[data-csv\]:only-child\) \{ flex-wrap: nowrap; align-items: flex-start; \}/);
  assert.match(read("src/pages/movers.css"), /\.mv-page \.k-chiprow\.wrap \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
});

test("LIVE12A-011: Breadth's range chips and + Custom are two even rows on a phone", () => {
  assert.match(read("src/styles.css"), /\.breadth-bar \.k-chiprow\.wrap \{ display: grid; grid-template-columns: repeat\(4, minmax\(0, 1fr\)\); gap: 6px; \}/);
});
