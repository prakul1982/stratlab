// fix13 (LIVE11A, 18 Nov 2026): the scored live review of Release 66. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE11A-001: a closed session's final read is not 'Reading the market again' hours later", async () => {
  const { moodStale, MOOD_STALE_SHUT } = await import("../src/lib/moodCache.ts");
  const now = Date.parse("2026-11-17T23:05:00Z");
  const old = new Date(now - (MOOD_STALE_SHUT + 12 * 3600) * 1000).toISOString();
  const m = { region: "IN", is_open: false, read_at: old, headline: "x", lines: [] };
  assert.equal(moodStale(m, now), true);                                   // not final: a fresh read is asked for
  assert.equal(moodStale({ ...m, final: true }, now), false);              // the session's final read: shown as it is
  assert.equal(moodStale({ ...m, final: true, refreshing: true }, now), true);
});

test("LIVE11A-019: the Usual move column goes when no answered row has one; zero-count index and F&O choices are not offered", async () => {
  const { movesEmpty } = await import("../src/lib/resultsRows.ts");
  const rows = Array.from({ length: 40 }, (_, i) => ({ symbol: `S${i}` }));
  const back = Object.fromEntries(rows.slice(0, 30).map((r) => [r.symbol, null]));          // 10 rows never answered in time
  assert.equal(movesEmpty(rows, back), true);
  assert.equal(movesEmpty(rows, { ...back, S3: { moves: { avg: 4 } } }), false);
  assert.equal(movesEmpty(rows, Object.fromEntries(rows.slice(0, 5).map((r) => [r.symbol, null]))), false);   // too few back yet
  assert.equal(movesEmpty([{ symbol: "A", moves: { avg: 1 } }], {}), false);
  const f = read("src/components/CalendarFilters.tsx");
  assert.match(f, /export const indexChoices = \(indices: Facets\["indices"\], picked: string\) => indices\.filter\(\(i\) => i\.count > 0 \|\| i\.id === picked\);/);
  assert.match(f, /facets\.fo != null && \(facets\.fo > 0 \|\| filters\.fo\)/);
  assert.match(read("src/pages/ResultsPage.tsx"), /const mvEmpty = movesEmpty\(shown, moves\);/);
});

test("LIVE11A-013: every stored theme is listed, without the market the tab names", async () => {
  const { libraryLabel } = await import("../src/lib/themeFormat.ts");
  assert.equal(libraryLabel({ name: "Cement", region: "IN", at: null, day: "2026-11-13" }, (d) => d, false), "Cement · updated 2026-11-13");
  assert.equal(libraryLabel({ name: "Cement", region: "IN", at: null, day: "2026-11-13" }, (d) => d), "Cement · India, updated 2026-11-13");
  const page = read("src/pages/ThemesPage.tsx");
  assert.doesNotMatch(page, /\.slice\(0, 4\);\n  if \(!shown\.length\) return null;/);
  assert.match(page, /All \{matching\.length\} themes/);
});

test("LIVE11A-014: one plan line for the download row, no toast with it, the decks count after the buttons", () => {
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /setSpent\(\(e as Error\)\.message \|\| "This month's decks are used\."\); setLock\("deck"\); \}\n      else fail\(e\);/);
  assert.match(dive, /locked=\{lock === "workbook"\} onLock=\{\(\) => setLock\("workbook"\)\}/);
  assert.match(dive, /locked=\{lock === "csv"\} onLock=\{\(\) => setLock\("csv"\)\}/);
  assert.ok(dive.indexOf('data-testid="decks-left"') > dive.indexOf("<ThemeCsvButton"));
});

test("LIVE11A-018/024: Breadth's CSV sits beside Alert me in the card head; the index card's column is 'When'", () => {
  const b = read("src/pages/BreadthPage.tsx");
  assert.match(b, /data-testid="breadth-today-tools">\n        \{!locked && <BreadthAlertButton group=\{group\} \/>\}\n        \{rows\.length > 0 && <CsvButton/);
  assert.match(read("src/pages/PulseMood.tsx"), /\{ key: "w", header: "When", cell: \(i\) => <span data-testid="index-when"/);
});

test("LIVE11A-023: a mid-size heatmap tile names a long symbol at 9px instead of leaving it blank", async () => {
  const { tileWords } = await import("../src/lib/heatmap.ts");
  const width = (text) => text.length * 6.5;
  assert.deepEqual(tileWords("POWERGRIDX", "+1.2%", 70, 50, width), { px: 9, fig: true });
  assert.deepEqual(tileWords("HINDUNILVR", "+1.2%", 60, 40, width), { px: 0, fig: false });
  assert.match(read("src/components/chart/Treemap.tsx"), /px === 9 \? " xs"/);
});

test("LIVE11A-029: a price this device read during a session that has closed is not shown under its 'last close' label", async () => {
  const { readInSession } = await import("../src/lib/marketDay.ts");
  const nse = { id: "NSE", tz: "Asia/Kolkata", hours: { open: "09:15", close: "15:30" }, holidays: [] };
  const night = new Date("2026-11-17T22:35:00Z");                                  // 04:05 IST Wed 18 Nov: shut, last session Tue 17 Nov
  assert.equal(readInSession(nse, "2026-11-17T08:50:00Z", night), true);          // 14:20 IST, during the session
  assert.equal(readInSession(nse, "2026-11-17T10:30:00Z", night), false);         // 16:00 IST, after the close
  assert.equal(readInSession(nse, "2026-11-17T08:50:00Z", new Date("2026-11-17T09:00:00Z")), false);   // still trading
  assert.match(read("src/components/watch/WatchPanel.tsx"), /return !!m && readInSession\(m, at\);/);
});

test("LIVE11A-022: the landing's sample cards show the server's verdict-first line when it has one", () => {
  const page = read("src/pages/Login.tsx");
  assert.match(page, /<span className="small">\{e\.verdict\.card_headline \?\? e\.verdict\.fact_headline \?\? e\.verdict\.headline\}<\/span>/);
  assert.match(page, /e\.verdict\.card_headline \?\? e\.verdict\.fact_headline \?\? e\.verdict\.headline\);/);
});

test("LIVE11A-027/028: the overnight data note is a quiet one; the sign-in gate doesn't name one way to sign in", () => {
  assert.match(read("src/main.tsx"), /<div className="banner data-banner calm" role="status"><span>Indian price data reconnects on \{back\}/);
  assert.match(read("src/styles.css"), /\.banner\.data-banner\.calm \{ background: var\(--chip\); color: var\(--muted\); \}/);
  assert.doesNotMatch(read("src/pages/Gate.tsx"), /Sign in with Google and this page opens/);
});
