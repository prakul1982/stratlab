// MWR-1: the review of Market Watch and the chart workspace. The forming candle in every market, the countdown that ends at the
// close, a daily candle that rolls over at the open, a timeframe change that keeps the moment on screen, the lists that stay one
// with the Research watchlist, the tabs a keyboard can use.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const T = await import("../src/charts/price/ticks.ts");
const { toBars, windowAround } = await import("../src/charts/price/transforms.ts");

const at = (iso) => Date.parse(iso);
const bar = (iso, o, h, l, c, v = 0) => toBars([{ t: iso, o, h, l, c, v }])[0];
const fresh = () => ({ cum: null });

// ---------- MWR1-001: no candle after the close in a market read every few seconds ----------
test("a price stamped at the close starts no candle in the US, UK, Europe or Japan, and one inside the session does", () => {
  const cases = [
    ["US", "-04:00", "15:59", "16:00", "15:30", "09:29"], ["UK", "+01:00", "16:29", "16:30", "16:00", "07:59"],
    ["EU", "+01:00", "17:29", "17:30", "17:00", "08:59"], ["JP", "+09:00", "15:29", "15:30", "15:00", "08:59"],
  ];
  for (const [market, off, lastMin, closeMin, inside, before] of cases) {
    const last = bar(`2026-10-23T${lastMin}:00${off}`, 100, 101, 99, 100);
    assert.equal(T.applyTick(last, { p: 100, v: null, t: at(`2026-10-23T${closeMin}:00${off}`) }, "1m", fresh(), market), null, `${market} closing print`);
    const mid = bar(`2026-10-23T${inside}:00${off}`, 100, 101, 99, 100);
    assert.equal(T.applyTick(mid, { p: 100.5, v: null, t: at(`2026-10-23T${inside}:30${off}`) }, "1m", fresh(), market).isNew, false, market);
    assert.equal(T.applyTick(mid, { p: 100.5, v: null, t: at(`2026-10-23T${inside.slice(0, 2)}:${String(+inside.slice(3) + 1).padStart(2, "0")}:05${off}`) }, "1m", fresh(), market).isNew, true, `${market} next minute`);
    assert.equal(T.applyTick(last, { p: 100, v: null, t: at(`2026-10-26T${before}:00${off}`) }, "1m", fresh(), market), null, `${market} before the open`);
  }
  // no candle on a Saturday or Sunday (a source that sent no time is read as now), in any market with a session
  const fri = bar("2026-10-23T15:59:00-04:00", 100, 101, 99, 100);
  assert.equal(T.applyTick(fri, { p: 100, v: null, t: at("2026-10-24T11:00:00-04:00") }, "1m", fresh(), "US"), null);
  const ist = bar("2026-10-23T15:29:00+05:30", 100, 101, 99, 100);
  assert.equal(T.applyTick(ist, { p: 100, v: null, t: at("2026-10-25T10:00:00+05:30") }, "1m", fresh(), "IN"), null);
  // crypto and forex trade round the clock: no session to keep inside
  const c = bar("2026-10-23T23:59:00+00:00", 100, 101, 99, 100);
  assert.equal(T.applyTick(c, { p: 100, v: null, t: at("2026-10-24T00:00:10+00:00") }, "1m", fresh(), "CRYPTO").isNew, true);
});

// ---------- MWR1-002: the countdown of a session's last candle ends at the close ----------
test("the last candle of a session counts down to the close, not to the end of its length", () => {
  const l30 = bar("2026-10-23T15:15:00+05:30", 1, 1, 1, 1);                                    // 15:15 to 15:45 on the grid, 15:30 on the clock
  assert.equal(T.closesIn(l30, "30m", at("2026-10-23T15:20:00+05:30"), "IN"), 600);
  assert.equal(T.closesIn(l30, "30m", at("2026-10-23T15:40:00+05:30"), "IN"), null);        // the market has closed: nothing is forming
  const l4h = bar("2026-10-23T13:15:00+05:30", 1, 1, 1, 1);
  assert.equal(T.closesIn(l4h, "4h", at("2026-10-23T14:00:00+05:30"), "IN"), 5400);
  assert.equal(T.closesIn(l4h, "4h", at("2026-10-23T15:45:00+05:30"), "IN"), null);
  const l2h = bar("2026-10-23T15:15:00+05:30", 1, 1, 1, 1);
  assert.equal(T.closesIn(l2h, "2h", at("2026-10-23T15:29:59+05:30"), "IN"), 1);
  // a candle that ends before the close is unchanged, and so is a market with no session
  const mid = bar("2026-10-23T10:15:00+05:30", 1, 1, 1, 1);
  assert.equal(T.closesIn(mid, "5m", at("2026-10-23T10:17:28+05:30"), "IN"), 152);
  const cr = bar("2026-10-23T23:30:00+00:00", 1, 1, 1, 1);
  assert.equal(T.closesIn(cr, "1h", at("2026-10-23T23:45:00+00:00"), "CRYPTO"), 2700);
  // MCX trades into the evening: its last candle ends at 23:30
  const mcx = bar("2026-10-23T23:15:00+05:30", 1, 1, 1, 1);
  assert.equal(T.closesIn(mcx, "30m", at("2026-10-23T23:20:00+05:30"), "MCX"), 600);
});

// ---------- MWR1-003: a daily chart left open over the open starts the new day's candle ----------
test("the first price of the next trading day starts its daily candle, inside the session only", () => {
  const fri = bar("2026-10-23T00:00:00+05:30", 100, 105, 98, 101, 9000);
  const vol = { cum: 50_000 };
  const mon = T.applyTick(fri, { p: 103, v: 1000, t: at("2026-10-26T09:16:05+05:30") }, "1d", vol, "IN");
  assert.equal(mon.isNew, true);
  assert.equal(mon.bar.t, at("2026-10-26T00:00:00+05:30"));                              // stamped at the day's midnight, as the broker stamps its daily candles
  assert.deepEqual([mon.bar.o, mon.bar.h, mon.bar.l, mon.bar.c], [103, 103, 103, 103]);
  assert.equal(mon.bar.w - mon.bar.t, fri.w - fri.t);
  // the next price moves it, and a tick from before the open or after the close starts nothing
  const more = T.applyTick(mon.bar, { p: 104.5, v: 1300, t: at("2026-10-26T09:17:10+05:30") }, "1d", vol, "IN");
  assert.deepEqual([more.isNew, more.bar.h, more.bar.c, more.bar.v], [false, 104.5, 104.5, 300]);
  assert.equal(T.applyTick(fri, { p: 103, v: null, t: at("2026-10-26T09:00:00+05:30") }, "1d", fresh(), "IN"), null);
  assert.equal(T.applyTick(fri, { p: 103, v: null, t: at("2026-10-26T15:31:00+05:30") }, "1d", fresh(), "IN"), null);
  // a price older than the candle is ignored
  assert.equal(T.applyTick(fri, { p: 103, v: null, t: at("2026-10-22T11:00:00+05:30") }, "1d", fresh(), "IN"), null);
  // and weekly or monthly candles are drawn from the daily ones, so a new week or month comes with the new day
  const w = bar("2026-10-19T00:00:00+05:30", 90, 99, 88, 95, 1);
  assert.equal(T.applyTick(w, { p: 96, v: null, t: at("2026-10-26T10:00:00+05:30") }, "1w", fresh(), "IN"), null);
});

// ---------- MWR1-004: a timeframe change keeps the moment on screen ----------
test("the window of candles around a moment sits inside the data and keeps its size", () => {
  assert.deepEqual(windowAround(1000, 500, 100), [450, 549]);
  assert.deepEqual(windowAround(1000, 10, 100), [0, 99]);              // near the start: the moment is left of the middle, the view stays on data
  assert.deepEqual(windowAround(1000, 995, 100), [900, 999]);
  assert.deepEqual(windowAround(40, 20, 100), [0, 39]);                // fewer candles than wanted: all of them
  assert.deepEqual(windowAround(1000, -5, 100), [0, 99]);
  const src = read("src/charts/price/PriceChart.tsx");
  assert.match(src, /keepView\.current = v && !v\.live \? \{ center: v\.center, count: v\.count \} : null/);       // not when the newest candle was in view
  assert.match(src, /void restoreView\(kv, req\)/);
  assert.match(src, /baseRef\.current\[0\]\.t > kv\.center/);                                                         // older pages are read until the moment is covered
  assert.match(src, /pages < 8/);                                                                                       // ...a few at most
  assert.match(src, /status === 429\) \{ window\.setTimeout\(\(\) => maybeMoreRef\.current\?\.\(\), 4000\)/);     // "a lot of reads" is a pause, not the end of the history (MWR1-013)
  const eng = read("src/charts/price/engine.ts");
  assert.match(eng, /viewSpan\(\)/);
  assert.match(eng, /showAround\(center: number, count: number\)/);
});

// ---------- MWR1-007: the first list and the Research watchlist stay one ----------
test("a change on either side is handed to the other, so a stale copy never replaces it", () => {
  const research = read("src/lib/research.ts");
  assert.match(research, /export function onWatchlistSaved/);
  assert.match(research, /export function adoptWatchlist/);
  assert.match(research, /method: "PUT", body: \{ items: list \} \}\); watchHear\.forEach/);        // announced only after the save went through
  const w = read("src/components/watch/useWatch.ts");
  assert.match(w, /onWatchlistSaved\(\(\) => \{ void reload\(\); \}\)/);                          // a star on a company page: the lists are read again
  assert.match(w, /adoptWatchlist\(first\.items\.filter/);                                         // a change in the panel: the Research copy follows
  assert.match(w, /i\.kind === "stock" \|\| i\.kind === "etf"/);                                   // only what the Research list can hold
});

// ---------- MWR1-008, 007: the panel's tabs and rows ----------
test("the list tabs move with the arrow keys and the tab row keeps its height", () => {
  const p = read("src/components/watch/WatchPanel.tsx");
  assert.match(p, /role="tablist" aria-label="Your lists" onKeyDown=\{tabKey\}/);
  for (const k of ["ArrowRight", "ArrowLeft", "Home", "End"]) assert.ok(p.includes(`"${k}"`), k);
  assert.match(p, /role="tabpanel" aria-labelledby=\{`mw-tab-\$\{listId\}`\}/);
  const css = read("src/components/watch/watch.css");
  assert.match(css, /\.mw-tabs \{ flex: none;/);                       // a column's overflow row shrank to nothing when the add box opened
  assert.match(css, /\.mw-bar \{ flex: none;/);
  assert.match(css, /\.mw-add \{ flex: none; max-height: 50%; overflow-y: auto;/);
});

// ---------- MWR1-014: a line of closes being read is read once ----------
test("the rows' lines of closes are asked for once while on their way", () => {
  const api = read("src/lib/watchApi.ts");
  assert.match(api, /const sparkWait = new Map<string, Promise<number\[\] \| undefined>>\(\)/);
  assert.match(api, /else if \(sparkWait\.has\(k\)\) waits\.push\(\[k, sparkWait\.get\(k\)!\]\)/);
  assert.match(api, /for \(const k of need\) sparkWait\.delete\(k\)/);
});
