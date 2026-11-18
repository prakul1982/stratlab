// Lane site76: the LIVE14A / LIVE14B site findings (live review after Release 75, Wed 18 Nov 2026). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const dayText = (iso) => `${Number(iso.slice(8, 10))} Nov`;

test("LIVE14A-001: a level the source stopped updating mid-session says its time, never 'Live' or 'today'", async () => {
  const { indexWhen, pulseClosedDay, pulseDelayedAt, pulseLede } = await import("../src/lib/research.ts");
  const at = "2026-11-18T15:52:50+00:00";
  const time = () => "10:52 ET";
  const rows = [{ name: "S&P 500", day: "2026-11-18", live: false, delayed: true, at }, { name: "NASDAQ", day: "2026-11-18", live: false, delayed: true, at }];
  assert.equal(indexWhen(rows[0], dayText, time), "as of 10:52 ET");
  assert.notEqual(indexWhen(rows[0], dayText), "today");
  assert.equal(pulseClosedDay(rows), null);                          // a session still trading is not "Last close, 18 Nov"
  assert.equal(pulseDelayedAt(rows), at);
  const lede = pulseLede(null, false, "10:52 ET");
  assert.match(lede, /^Index levels as of 10:52 ET/);
  assert.doesNotMatch(lede, /Live/);
  // a live level reads as before
  assert.equal(indexWhen({ day: "2026-11-18", live: true }, dayText, time), "today");
  assert.equal(pulseDelayedAt([{ live: true, at }]), null);
  assert.match(pulseLede(null), /^Live index levels/);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /useLiveRefresh\(!!data\?\.indices\.some\(\(i\) => i\.live \|\| i\.delayed\)/);     // asked again while delayed
});

test("LIVE14A-001: a results row priced long ago in the session carries its time, and the footer says the prices are not live", async () => {
  const { quoteDelayed } = await import("../src/lib/rowReads.ts");
  const { pricesNote } = await import("../src/lib/rowReads.ts");
  const now = Date.parse("2026-11-18T19:30:00Z");
  const t = () => "10:52 ET";
  assert.equal(quoteDelayed("2026-11-18T15:52:49Z", true, t, now), "as of 10:52 ET");
  assert.equal(quoteDelayed("2026-11-18T19:28:00Z", true, t, now), null);          // two minutes old: live
  assert.equal(quoteDelayed("2026-11-18T15:52:49Z", false, t, now), null);         // market shut: the footer says last close
  const note = pricesNote({ live: false, asOf: "10:52 ET", rows: 30, cap: 1000, closeDay: "2026-11-18", older: 0, olderDay: null, open: true, behind: true }, dayText);
  assert.match(note, /^Prices as of 10:52 ET, the latest the price source has sent: not live/);
  assert.doesNotMatch(note, /not trading now/);
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /data-testid="res-px-at"/);
});

test("LIVE14A-009: Usual move per day's table; the quarter before the one being reported says so", async () => {
  const { movesEmpty, priorQuarter } = await import("../src/lib/resultsRows.ts");
  // a day table of 12 rows, all answered, one with a usual move: no column for that table
  const rows = Array.from({ length: 12 }, (_, i) => ({ symbol: `S${i}` }));
  const back = Object.fromEntries(rows.map((r, i) => [r.symbol, i === 0 ? { moves: { avg: 16.7 } } : null]));
  assert.equal(movesEmpty(rows, back, rows.length), true);
  assert.equal(movesEmpty(rows, { ...back, S1: { moves: { avg: 2 } }, S2: { moves: { avg: 3 } } }, rows.length), false);
  assert.equal(movesEmpty(rows, { S0: { moves: { avg: 1 } } }, rows.length), false);       // still being read: the column stays
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /c\.key !== "mv" \|\| !movesEmpty\(on, moves, on\.length\)/);
  // PANW on 18 Nov: figures to Jul 2026 (110 days before) are the previous quarter's; TJX's to Oct 2026 are the one reported
  assert.equal(priorQuarter("Jul 2026 vs Jul 2025", "2026-11-18"), "Jul 2026");
  assert.equal(priorQuarter("Oct 2026 vs Oct 2025", "2026-11-18"), null);
  assert.equal(priorQuarter("Sep 2026 vs Sep 2025", "2026-11-10"), null);                 // India: 41 days after the quarter
  assert.equal(priorQuarter("Jun 2026 vs Jun 2025", "2026-11-10"), "Jun 2026");
  assert.equal(priorQuarter(null, "2026-11-18"), null);
  assert.match(page, /data-testid="res-q-prior">previous quarter, to \{p\}/);
});

test("LIVE14A-013: an open Indian issue without its lot or bids says why (the issue page found or not, read or not, and when)", () => {
  const page = read("src/pages/IposPage.tsx");
  assert.match(page, /if \(r\?\.page === false\) return "No NSE issue page for it yet \(the lot and bids are read there\)";/);
  assert.match(page, /if \(r\?\.page && !r\.page_at\) return "NSE's issue page not read yet";/);
  assert.match(page, /if \(r\?\.page_at\) return `Not on NSE's issue page, read \$\{readAt\(r\.page_at\)\}`;/);
  assert.match(page, /tab === "open" && m === "IN" \? <span className="k-muted" data-testid="ipo-bids-none">\{bidsMissing\(r\)\}<\/span>/);
});
