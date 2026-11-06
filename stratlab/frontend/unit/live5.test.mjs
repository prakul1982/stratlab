// LIVE5 (re-score after Release 13, 6 Nov 2026): the fixes that can be checked without a browser.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { pricesNote, quoteAsk, readRows, sessionDayOf } from "../src/lib/rowReads.ts";

// a source file's own imports name no extension ("./api"): try ".ts" (as unit/live4-ui.test.mjs does)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const day = (iso) => ({ "2026-11-05": "Thu 5 Nov", "2026-11-06": "Fri 6 Nov" })[iso] ?? iso;

test("LIVE5-001: a stock the server's price source was busy for is asked again until it has a price; a failed call too", async () => {
  const calls = [];
  let round = 0;
  const ask = quoteAsk(async (part) => {
    calls.push(part);
    round += 1;
    if (round === 2) throw new Error("503");                       // a call that failed: its rows are asked again, not a dash
    // the first call: half the stocks past the source's budget (pending); later calls answer everything
    const busy = round === 1 ? part.filter((_, i) => i % 2) : [];
    return { quotes: Object.fromEntries(part.filter((s) => !busy.includes(s)).map((s) => [s, { price: 10, at: "2026-11-06T10:00:00Z" }])), pending: busy };
  });
  const put = {};
  const list = Array.from({ length: 6 }, (_, i) => `S${i}`);
  await readRows(list, ask, (got) => Object.assign(put, got), { size: 6, parallel: 1, deadlineMs: 2000, pauseMs: 10 });
  for (const s of list) assert.equal(put[s]?.price, 10, s);          // every row priced: none kept the day before's close
  assert.equal(calls.length, 3);
});

test("LIVE5-001: a stock answered with no price is a dash at once; the answer under the asked ticker is found", async () => {
  const ask = quoteAsk(async () => ({ quotes: { ABB: { price: 6774, at: "x" }, OIL: null, "BRK.B": { price: 1 } }, pending: [] }));
  const got = await ask(["ABB", "OIL", "brk.b"]);
  assert.deepEqual(got.pending, []);
  assert.equal(got.got.ABB.price, 6774);
  assert.equal(got.got.OIL, null);
  assert.equal(got.got["brk.b"].price, 1);
});

test("LIVE5-001: the session the prices are of is the newest read's day in the market's zone", () => {
  // 15:29 IST on 6 Nov is 09:59 UTC; 23:50 UTC on 5 Nov is 05:20 IST on 6 Nov
  assert.equal(sessionDayOf(["2026-11-05T09:59:00Z", "2026-11-06T09:59:00Z", null], "Asia/Kolkata"), "2026-11-06");
  assert.equal(sessionDayOf(["2026-11-05T23:50:00Z"], "Asia/Kolkata"), "2026-11-06");
  assert.equal(sessionDayOf(["2026-11-05T23:50:00Z"], "America/New_York"), "2026-11-05");
  assert.equal(sessionDayOf([], "Asia/Kolkata"), null);
});

test("LIVE5-001: the footer names the day of the prices shown and counts the rows still on an older close", () => {
  const base = { live: false, asOf: null, rows: 76, cap: 1000, closeDay: "2026-11-06", older: 0, olderDay: null };
  assert.equal(pricesNote(base, day), "Prices are each company's last close, Fri 6 Nov; the market is not trading now.");
  assert.equal(pricesNote({ ...base, older: 3, olderDay: "2026-11-05", reading: true }, day),
    "Prices are each company's last close, Fri 6 Nov; the market is not trading now. 3 companies' prices are still being read; they show the close of Thu 5 Nov, in grey.");
  assert.match(pricesNote({ ...base, older: 1, olderDay: "2026-11-05" }, day), /1 company's price couldn't be read just now; it shows the close of Thu 5 Nov/);
  assert.equal(pricesNote({ ...base, live: true, asOf: "10:31 IST" }, day),
    "Prices as of 10:31 IST, read for the 76 companies shown and again each minute while the market trades.");
  assert.equal(pricesNote({ ...base, rows: 0 }, day), "");
});

test("LIVE5-011: no arrow on a change that prints as zero, an arrow on one that doesn't", async () => {
  const { arrowOf } = await import("../src/lib/format.ts");
  assert.equal(arrowOf(0.04, "0.0"), "");
  assert.equal(arrowOf(-0.04, "0.0%"), "");
  assert.equal(arrowOf(0, "0.0"), "");
  assert.equal(arrowOf(0.06, "0.1"), "▲");
  assert.equal(arrowOf(-3.4, "3.4%"), "▼");
  assert.equal(arrowOf(null), "");
});

test("LIVE5-002: the results day fits a 1280 and a 1024 screen: market value then the quarter leave a narrow table, the name has its own line", () => {
  const page = readFileSync(new URL("../src/pages/ResultsPage.tsx", import.meta.url), "utf8");
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  const inv = readFileSync(new URL("../src/styles-invest.css", import.meta.url), "utf8");
  assert.match(page, /key: "cap", header: "Market value", numeric: true, phone: false, narrow: false/);
  assert.match(page, /key: "q", header: "Quarter", [^\n]*tight: false/);
  assert.match(page, /key: "im", header: "Implied"/);
  assert.match(css, /\.k-tbl-wrap\.has-narrow \{ container-type: inline-size; \}/);
  assert.match(css, /@container \(max-width: 899px\) \{ \.k-table th\.k-narrow-off, \.k-table td\.k-narrow-off \{ display: none; \} \}/);
  assert.match(inv, /\.res-co \{ [^}]*min-width: 11rem;/);
  assert.match(inv, /\.res-mv-top \{ display: flex; flex-wrap: wrap;/);
  assert.doesNotMatch(page, /v > 0 \? "▲" : v < 0 \? "▼"/);
});

test("LIVE5-003: the live round's 52-week highs and lows fill today's column; after the close a round without them says 'This evening'", async () => {
  const { cardTable } = await import("../src/lib/breadth.ts");
  const fig = (value, prev) => ({ value, prev, change: null });
  const today = { day: "2026-11-05", prev_day: "2026-11-04", adv: fig(359, 300), dec: fig(138, 200), pct50: fig(46.4, 44.0), highs: fig(24, 20), lows: fig(3, 5) };
  const final = { state: "final", day: "2026-11-06", as_of: "15:30", latest: { adv: 228, dec: 268, pct50: 41.0, hi: 9, lo: 14 } };
  const t = cardTable({ today, live: final });
  assert.equal(t.nowHead, "Today, 6 Nov");
  assert.deepEqual(t.rows.find((r) => r.id === "hl"), { id: "hl", k: "52-week highs / lows", now: "9 / 14", before: "24 / 3" });
  const old = cardTable({ today, live: { ...final, latest: { adv: 228, dec: 268, pct50: 41.0 } } });
  assert.equal(old.rows.find((r) => r.id === "hl").now, null);
  assert.equal(old.waiting, "This evening");
  const mood = readFileSync(new URL("../src/pages/PulseMood.tsx", import.meta.url), "utf8");
  assert.match(mood, /const when = b\.live && open \? "so far today" : `on \$\{day\(b\.day\)\}`;/);     // LIVE5-009
  assert.match(mood, /const waiting = open \? "At the close" : "This evening";/);
});

test("LIVE5-006/007: Market Watch says the last close's day once its markets are shut; visitors get no floating button", async () => {
  const { asOfLine } = await import("../src/lib/watch.ts");
  // 15:29:59 IST on Fri 6 Nov, read again at 16:29
  assert.equal(asOfLine(["2026-11-06T09:59:59Z", "2026-11-06T10:59:39Z"], "Asia/Kolkata", true), "Closed · last close Fri 6 Nov");
  assert.equal(asOfLine(["2026-11-06T21:00:00Z"], "America/New_York", true), "Closed · last close Fri 6 Nov");
  assert.equal(asOfLine(["2026-11-06T04:59:39Z"]), "Prices as of 10:29:39 IST");
  const visitor = readFileSync(new URL("../src/visitor/VisitorApp.tsx", import.meta.url), "utf8");
  assert.match(visitor, /\{userId && <PublicMarkets userId=\{userId\} \/>\}/);
  const launcher = readFileSync(new URL("../src/components/watch/Launcher.tsx", import.meta.url), "utf8");
  assert.match(launcher, /if \(shown && shapeOf\(layout, window\.innerWidth\) !== "dock"\) close\(\);/);
  const css = readFileSync(new URL("../src/components/watch/launcher.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 900px\) \{\n  \.mw-launch\.app, \.mw-launch\.public \{ display: none; \}/);
});

test("LIVE5-008: rotation's gaps over the benchmark are points, and its chart and Admin's jobs hold their place while loading", async () => {
  const scans = readFileSync(new URL("../src/pages/ResearchScans.tsx", import.meta.url), "utf8");
  assert.match(scans, /\{ w1: "1W, pts", m1: "1M, pts", m3: "3M, pts" \}/);
  assert.match(scans, /<Delta value=\{r\.ret\[k\]!\}>\{ptsText\(r\.ret\[k\]!\)\}<\/Delta>/);
  assert.match(scans, /<Skeleton label="Comparing each one with the market" lines=\{4\} page \/>/);
  assert.match(scans, /asOfPending=\{!out && !failed\}/);
  assert.match(readFileSync(new URL("../src/pages/admin/DataSection.tsx", import.meta.url), "utf8"), /<Skeleton label="Loading the jobs" page \/>/);
  const ptsText = (v) => { const t = Math.abs(v).toFixed(2); return /[1-9]/.test(t) ? `${v > 0 ? "+" : "−"}${t}` : t; };
  assert.match(scans, /export const ptsText = \(v: number\): string => \{ const t = Math\.abs\(v\)\.toFixed\(2\); return \/\[1-9\]\/\.test\(t\) \? `\$\{v > 0 \? "\+" : "−"\}\$\{t\}` : t; \};/);
  assert.equal(ptsText(3.274), "+3.27");
  assert.equal(ptsText(-0.001), "0.00");
});
