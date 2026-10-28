// MW-1: Market Watch and the chart workspace. The forming candle from ticks, the watchlist rules (items, sorting, moving, limits
// said before they bite), the panel's place, the live client (a stream, reads every few seconds, a drop), the drawing round trip,
// and that the panel is drawn once in the Shell and never in the public half's first download.
// Run: npm run test:unit
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const T = await import("../src/charts/price/ticks.ts");
const W = await import("../src/lib/watch.ts");
const L = await import("../src/lib/watchLayout.ts");
const Live = await import("../src/lib/watchLive.ts");
const { toBars, dayOf } = await import("../src/charts/price/transforms.ts");
const { cleanDrawings } = await import("../src/charts/price/drawGeo.ts");
const { cleanLayout } = await import("../src/charts/price/drawChoose.ts");

const IST = 5.5 * 3600_000;
const at = (iso) => Date.parse(iso);
/** One India 1-minute candle, from an ISO time with the offset. */
const bar = (iso, o, h, l, c, v = 0) => { const [x] = toBars([{ t: iso, o, h, l, c, v }]); return x; };

// ---------- the forming candle ----------
test("a tick moves the newest candle: close, high, low and the volume since the last tick", () => {
  const last = bar("2026-10-23T10:15:00+05:30", 100, 101, 99, 100.5, 5000);
  const vol = { cum: null };
  const a = T.applyTick(last, { p: 102, v: 20_000, t: at("2026-10-23T10:15:20+05:30") }, "1m", vol);
  assert.equal(a.isNew, false);
  assert.deepEqual([a.bar.o, a.bar.h, a.bar.l, a.bar.c, a.bar.v], [100, 102, 99, 102, 5000]);          // the first tick only sets the mark
  const b = T.applyTick(a.bar, { p: 98.5, v: 20_450, t: at("2026-10-23T10:15:40+05:30") }, "1m", vol);
  assert.deepEqual([b.bar.h, b.bar.l, b.bar.c, b.bar.v], [102, 98.5, 98.5, 5450]);                      // +450 traded since
});

test("a tick after the candle's end starts the next one on the same grid, and not past the session", () => {
  const last = bar("2026-10-23T10:15:00+05:30", 100, 101, 99, 100.5, 5000);
  const vol = { cum: 1000 };
  const n = T.applyTick(last, { p: 103, v: 1300, t: at("2026-10-23T10:16:02+05:30") }, "1m", vol);
  assert.equal(n.isNew, true);
  assert.equal(n.bar.t, at("2026-10-23T10:16:00+05:30"));
  assert.deepEqual([n.bar.o, n.bar.h, n.bar.l, n.bar.c, n.bar.v], [103, 103, 103, 103, 300]);
  assert.equal(n.bar.w - n.bar.t, last.w - last.t);                                                      // the exchange's clock carries over
  // 5-minute candles: 10:21 is in the 10:20 candle
  const five = bar("2026-10-23T10:15:00+05:30", 100, 101, 99, 100, 0);
  const f = T.applyTick(five, { p: 101, v: null, t: at("2026-10-23T10:21:30+05:30") }, "5m", { cum: null });
  assert.equal(f.bar.t, at("2026-10-23T10:20:00+05:30"));
  // a tick after 15:30 starts no candle (the closing auction), and nor does one before the open
  const closing = bar("2026-10-23T15:29:00+05:30", 100, 101, 99, 100, 0);
  assert.equal(T.applyTick(closing, { p: 100, v: null, t: at("2026-10-23T15:31:00+05:30") }, "1m", { cum: null }), null);
  assert.equal(T.applyTick(closing, { p: 100, v: null, t: at("2026-10-23T15:29:30+05:30") }, "1m", { cum: null }).isNew, false);
  assert.equal(T.applyTick(closing, { p: 100, v: null, t: at("2026-10-24T09:00:00+05:30") }, "1m", { cum: null }), null);
  assert.equal(T.applyTick(closing, { p: 100, v: null, t: at("2026-10-24T09:15:05+05:30") }, "1m", { cum: null }).bar.t, at("2026-10-24T09:15:00+05:30"));
  // an older tick, or a made-up one, is ignored
  assert.equal(T.applyTick(closing, { p: 100, v: null, t: at("2026-10-23T15:10:00+05:30") }, "1m", { cum: null }), null);
  assert.equal(T.applyTick(closing, { p: NaN, v: null, t: Date.now() }, "1m", { cum: null }), null);
  assert.equal(T.applyTick(undefined, { p: 1, v: null, t: Date.now() }, "1m", { cum: null }), null);
});

test("a daily, weekly or monthly candle takes ticks only inside its own day, week or month", () => {
  const d = bar("2026-10-23T00:00:00+05:30", 100, 105, 98, 101, 9000);
  const same = T.applyTick(d, { p: 107, v: null, t: at("2026-10-23T12:00:00+05:30") }, "1d", { cum: null });
  assert.deepEqual([same.bar.h, same.bar.c, same.isNew], [107, 107, false]);
  assert.equal(T.applyTick(d, { p: 107, v: null, t: at("2026-10-24T10:00:00+05:30") }, "1d", { cum: null }), null);
  const w = bar("2026-10-19T00:00:00+05:30", 90, 99, 88, 95, 1);
  assert.ok(T.applyTick(w, { p: 96, v: null, t: at("2026-10-23T10:00:00+05:30") }, "1w", { cum: null }));
  assert.equal(T.applyTick(w, { p: 96, v: null, t: at("2026-10-26T10:00:00+05:30") }, "1w", { cum: null }), null);
  const m = bar("2026-10-01T00:00:00+05:30", 90, 99, 88, 95, 1);
  assert.ok(T.applyTick(m, { p: 96, v: null, t: at("2026-10-30T10:00:00+05:30") }, "1mo", { cum: null }));
  assert.equal(T.applyTick(m, { p: 96, v: null, t: at("2026-11-02T10:00:00+05:30") }, "1mo", { cum: null }), null);
});

test("volume since the last tick: the first only sets the mark and a lower total is a new day", () => {
  const s = { cum: null };
  assert.equal(T.volumeSince(s, 1000), 0);
  assert.equal(T.volumeSince(s, 1250), 250);
  assert.equal(T.volumeSince(s, 1250), 0);
  assert.equal(T.volumeSince(s, 80), 0);          // the next day started again
  assert.equal(T.volumeSince(s, 130), 50);
  assert.equal(T.volumeSince(s, null), 0);
  assert.equal(s.cum, 130);
});

test("the countdown to a candle's close, and the timeframe keys", () => {
  const last = bar("2026-10-23T10:15:00+05:30", 1, 1, 1, 1);
  assert.equal(T.closesIn(last, "5m", at("2026-10-23T10:17:28+05:30")), 152);
  assert.equal(T.closesIn(last, "5m", at("2026-10-23T10:20:00+05:30")), null);          // no candle forming: the market is shut
  assert.equal(T.closesIn(last, "5m", at("2026-10-23T10:14:00+05:30")), null);
  assert.equal(T.closesIn(last, "1d", at("2026-10-23T10:17:28+05:30")), null);
  assert.equal(T.countdown(152), "2:32");
  assert.equal(T.countdown(59), "0:59");
  assert.equal(T.countdown(3725), "1:02:05");
  assert.equal(T.stepTf(["1m", "5m", "1h"], "5m", 1), "1h");
  assert.equal(T.stepTf(["1m", "5m", "1h"], "1h", 1), "1h");
  assert.equal(T.stepTf(["1m", "5m", "1h"], "1m", -1), "1m");
  assert.equal(T.stepTf(["1m", "5m", "1h"], "4h", 1), "1m");
  assert.deepEqual(["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"].map((k) => T.TF_KEYS[k]), ["1m", "3m", "5m", "10m", "15m", "30m", "1h", "4h", "1d", "1w"]);
  assert.equal(T.WORKSPACE_TFS.length, 12);
  assert.ok(Object.values(T.TF_KEYS).every((t) => T.WORKSPACE_TFS.includes(t)));
});

test("a chart that sizes its candles by the clock keeps a grid whatever day the first candle was", () => {
  // every timeframe's length divides a day, so a candle grid from any candle of a day lines up with the next day's open
  for (const [tf, ms] of Object.entries(T.TF_MS)) if (ms) assert.equal(86_400_000 % ms, 0, tf);
  assert.equal(dayOf(0), 0);
});

// ---------- list items, rules and words ----------
test("an instrument from the search becomes a list item, and the ones a list cannot hold do not", () => {
  const item = (i) => W.itemOf({ symbol: "X", ...i });
  assert.deepEqual(item({ id: "IN:738561", market: "IN", type: "EQ", symbol: "RELIANCE", name: "Reliance Industries" }),
    { id: "IN:RELIANCE", market: "IN", symbol: "RELIANCE", name: "Reliance Industries", kind: "stock" });
  assert.equal(item({ id: "IN:1", market: "IN", type: "ETF", symbol: "NIFTYBEES", etf: true }).kind, "etf");
  assert.equal(item({ id: "IN:256265", market: "IN", type: "INDEX", symbol: "NIFTY 50" }).id, "IN:^NSEI");
  assert.equal(item({ id: "IN:9", market: "IN", type: "INDEX", symbol: "NIFTY BANK" }).id, "IN:^NSEBANK");
  assert.equal(item({ id: "IN:9", market: "IN", type: "INDEX", symbol: "NIFTY IT" }), null);          // only the indices it can chart
  assert.equal(item({ id: "IN:77", market: "IN", type: "FUT", symbol: "NIFTY26NOVFUT" }), null);       // a contract: its underlying is the thing to list
  assert.equal(item({ id: "IN:78", market: "IN", type: "CE", symbol: "NIFTY26NOV22600CE" }), null);
  assert.equal(item({ id: "US:AAPL", market: "US", type: "EQ", symbol: "AAPL", name: "Apple" }).id, "US:AAPL");
  assert.equal(item({ id: "CRYPTO:BTC-USD", market: "CRYPTO", type: "CRYPTO", symbol: "BTC/USD", name: "Bitcoin / US Dollar" }).symbol, "BTC-USD");
  assert.equal(item({ id: "FX:EURUSD=X", market: "FX", type: "FX", symbol: "EUR/USD" }).id, "FX:EURUSD=X");
  assert.equal(item({ id: "CMDTY:GC=F", market: "CMDTY", type: "FUT", symbol: "GC=F" }).kind, "commodity");
  assert.equal(item({ id: "MCX:GOLDM", market: "MCX", type: "FUT", symbol: "GOLDM", name: "Gold Mini" }).kind, "future");
  assert.equal(item({ id: "CSV:x", market: "CSV", type: "X", symbol: "X" }), null);
  assert.equal(item({ id: "UK:SHEL.L", market: "UK", type: "EQ", symbol: "SHEL.L" }).id, "UK:SHEL.L");
});

test("rows are named the way people say them", () => {
  const l = (market, symbol, name, kind) => W.labelOf({ id: `${market}:${symbol}`, market, symbol, name, kind });
  assert.equal(l("FX", "EURUSD=X", "Euro / US Dollar", "fx"), "EUR/USD");
  assert.equal(l("CRYPTO", "BTC-USD", "Bitcoin / US Dollar", "crypto"), "BTC/USD");
  assert.equal(l("IN", "^NSEI", "NIFTY 50", "index"), "NIFTY 50");
  assert.equal(l("CMDTY", "GC=F", "Gold futures (COMEX, $ per ounce)", "commodity"), "Gold");
  assert.equal(l("IN", "RELIANCE", "Reliance Industries", "stock"), "RELIANCE");
  assert.equal(W.subtitleOf({ id: "IN:RELIANCE", market: "IN", symbol: "RELIANCE", name: "Reliance Industries", kind: "stock" }), "Reliance Industries");
  assert.equal(W.subtitleOf({ id: "IN:^NSEI", market: "IN", symbol: "^NSEI", name: "NIFTY 50", kind: "index" }), "India index");
  assert.equal(W.subtitleOf({ id: "CRYPTO:BTC-USD", market: "CRYPTO", symbol: "BTC-USD", name: "BTC-USD", kind: "crypto" }), "Crypto");
  for (const p of W.POPULAR) assert.ok(!/yahoo|finnhub|screener|coinbase|kite|zerodha/i.test(`${p.name} ${W.labelOf(p)}`), p.id);
});

test("where an item's chart is and how it reads its candles", () => {
  const rel = { id: "IN:RELIANCE", market: "IN", symbol: "RELIANCE", name: "x", kind: "stock" };
  assert.equal(W.chartPath(rel), "/chart/IN/RELIANCE");
  assert.equal(W.chartPath({ market: "IN", symbol: "^NSEI" }), "/chart/IN/%5ENSEI");
  assert.equal(W.chartPath({ market: "FX", symbol: "EURUSD=X" }), "/chart/FX/EURUSD%3DX");
  assert.deepEqual(W.chartSource(rel), { kind: "company", region: "IN", symbol: "RELIANCE", storageKey: "IN:RELIANCE" });
  assert.deepEqual(W.chartSource({ id: "CRYPTO:BTC-USD", market: "CRYPTO", symbol: "BTC-USD" }), { kind: "instrument", id: "CRYPTO:BTC-USD", storageKey: "CRYPTO:BTC-USD" });
  const back = W.itemFromPath("in", "%5ENSEI");
  assert.deepEqual([back.id, back.name, back.kind], ["IN:^NSEI", "NIFTY 50", "index"]);
  assert.equal(W.itemFromPath("fx", "EURUSD%3DX").id, "FX:EURUSD=X");
  assert.equal(W.currencyOf({ market: "IN", symbol: "X" }), "INR");
  assert.equal(W.currencyOf({ market: "CRYPTO", symbol: "BTC-EUR" }), "EUR");
  assert.equal(W.currencyOf({ market: "FX", symbol: "USDJPY=X" }), "JPY");
  assert.ok(W.STREAMED.includes("IN") && !W.STREAMED.includes("US"));
});

test("sorting by the day's change, moving, and the numbers shown", () => {
  const mk = (s) => ({ id: `IN:${s}`, market: "IN", symbol: s, name: s, kind: "stock" });
  const items = ["A", "B", "C", "D"].map(mk);
  const ch = { "IN:A": 1.5, "IN:B": -2, "IN:C": null, "IN:D": 4 };
  const by = (m) => W.sortItems(items, m, (it) => ch[it.id]).map((i) => i.symbol).join("");
  assert.equal(by("custom"), "ABCD");
  assert.equal(by("change_desc"), "DABC");          // a row with no change goes last either way
  assert.equal(by("change_asc"), "BADC");
  assert.equal(by("name"), "ABCD");
  assert.deepEqual(W.moveItem(["a", "b", "c", "d"], 3, 0), ["d", "a", "b", "c"]);
  assert.deepEqual(W.moveItem(["a", "b", "c"], 0, 5), ["b", "c", "a"]);
  assert.deepEqual(W.moveItem(["a", "b"], 1, 1), ["a", "b"]);
  assert.equal(W.changeText(1.234), "+1.23%");
  assert.equal(W.changeText(-0.4), "−0.40%");
  assert.equal(W.changeText(0.001), "0.00%");
  assert.equal(W.changeText(null), "–");
  assert.ok(Math.abs(W.changeOf({ price: 110, prev_close: 100, change_pct: 0 }, 105) - 5) < 1e-9);          // a live price moves the change; the previous close stays
  assert.equal(W.changeOf({ price: 110, prev_close: null, change_pct: 3.2 }), 3.2);
  assert.equal(W.changeOf(undefined), null);
  assert.equal(W.priceText(1234.5, "INR", "IN", "X"), "1,234.50");
  assert.equal(W.priceText(1.08123456, "USD", "FX", "EURUSD=X"), "1.08123");
  assert.equal(W.priceText(150.123, "JPY", "FX", "USDJPY=X"), "150.123");
  assert.equal(W.priceText(0.000123, "USD", "CRYPTO", "X-USD"), "0.00012300");
});

// ---------- the plans' limits, said before they bite ----------
test("the numbers on the plans: Free 1 list of 20 and 3 charts and 3 indicators, Basic 10 lists of 100, Pro none", async () => {
  const { LIMITS, NUMBERS } = await import("../src/lib/plans.ts");
  assert.deepEqual([LIMITS.free.watchlists, LIMITS.free.watchlist_symbols, LIMITS.free.chart_saves, LIMITS.free.chart_indicators], [1, 20, 3, 3]);
  assert.deepEqual([LIMITS.basic.watchlists, LIMITS.basic.watchlist_symbols, LIMITS.basic.chart_saves, LIMITS.basic.chart_indicators], [10, 100, null, 10]);
  assert.deepEqual([LIMITS.pro.watchlists, LIMITS.pro.watchlist_symbols, LIMITS.pro.chart_saves, LIMITS.pro.chart_indicators], [null, null, null, null]);
  const shown = NUMBERS.map(([k]) => k);
  for (const k of ["watchlists", "watchlist_symbols", "chart_saves", "chart_indicators"]) assert.ok(shown.includes(k), `${k} is on the Plans page`);
});

test("a limit says what the plan keeps and what the next one does, before it is met", () => {
  const lim = { lists: 1, symbols: 20, charts: 3, indicators: 3, next: { lists: "Basic", symbols: "Basic", charts: "Basic", indicators: "Basic" } };
  assert.equal(W.symbolsSaid(lim, 10, "Free"), null);                                          // plenty of room: nothing said
  assert.equal(W.symbolsSaid(lim, 17, "Free"), "17 of 20 symbols on Free. Basic keeps 100.");   // near the end
  assert.equal(W.symbolsSaid(lim, 20, "Free"), "20 of 20 symbols on Free. Basic keeps 100.");
  assert.equal(W.symbolsSaid({ ...lim, symbols: null }, 500, "Pro"), null);
  assert.equal(W.listsSaid(lim, 1, "Free"), "Free keeps 1 list. Basic keeps 10.");
  assert.equal(W.listsSaid({ ...lim, lists: 10, next: { ...lim.next, lists: "Pro" } }, 10, "Basic"), "Basic keeps 10 lists. Pro has no limit.");
  assert.equal(W.listsSaid({ ...lim, lists: 10 }, 4, "Basic"), null);
  assert.equal(W.indicatorsSaid(lim, 2, "Free"), null);
  assert.equal(W.indicatorsSaid(lim, 3, "Free"), "Free keeps 3 indicators on a chart. Basic keeps 10.");
  assert.equal(W.indicatorsSaid({ indicators: null, next: { indicators: null } }, 40, "Pro"), null);
  assert.equal(W.chartsSaid(3, 1, false, "Basic", "Free"), null);
  assert.equal(W.chartsSaid(3, 2, false, "Basic", "Free"), "Drawings and indicators are kept on 2 of 3 charts on Free. This is the last one.");
  assert.match(W.chartsSaid(3, 3, false, "Basic", "Free"), /won't be kept: Free keeps 3 charts\. Basic has no limit\./);
  assert.equal(W.chartsSaid(3, 3, true, "Basic", "Free"), null);                                // this chart is already one of them
  assert.equal(W.chartsSaid(null, 99, false, null, "Pro"), null);
  assert.equal(W.nextPlanWith("free", "watchlists"), "Basic");
  assert.equal(W.nextPlanWith("basic", "watchlists"), "Pro");
  assert.equal(W.nextPlanWith("pro", "watchlists"), null);
  assert.equal(W.nextPlanWith("basic", "chart_saves"), null);
  for (const said of [W.symbolsSaid(lim, 20, "Free"), W.listsSaid(lim, 1, "Free"), W.indicatorsSaid(lim, 3, "Free")]) assert.doesNotMatch(said, /\b(buy|sell|hold|target)\b/i);
});

// ---------- the panel's place ----------
test("the panel's layout is kept safe: unknown values dropped, sizes inside the window", () => {
  const d = L.clampLayout(null, 1440, 900);
  assert.deepEqual(d, L.DEFAULT_LAYOUT);
  const big = L.clampLayout({ open: true, mode: "float", w: 9999, h: 9999, x: 5000, y: -4, list: "abc", sort: "change_desc", chart: "IN:RELIANCE" }, 1280, 800);
  assert.equal(big.open, true); assert.equal(big.mode, "float");
  assert.ok(big.w <= 720 && big.w >= 300 && big.h <= 768);
  assert.ok(big.x >= 0 && big.x + big.w <= 1280 && big.y >= 0 && big.y + big.h <= 800);
  assert.deepEqual([big.list, big.sort, big.chart], ["abc", "change_desc", "IN:RELIANCE"]);
  const bad = L.clampLayout({ open: "yes", mode: "wide", w: "a", sort: "zzz", chart: "<script>", list: 5 }, 1280, 800);
  assert.deepEqual([bad.open, bad.mode, bad.w, bad.sort, bad.chart, bad.list], [false, "dock", 380, "custom", null, null]);
  const small = L.clampLayout({ w: 700 }, 600, 700);
  assert.ok(small.w <= 520 && small.w >= 300);
  assert.equal(L.isSheet(390), true); assert.equal(L.isSheet(900), true); assert.equal(L.isSheet(901), false);
});

test("a docked panel makes room, a floating one and a sheet do not; dragging and sizing stay inside the window", () => {
  const dock = { ...L.DEFAULT_LAYOUT, open: true, mode: "dock", w: 400 };
  assert.equal(L.dockWidth(dock, 1920), 400);
  assert.equal(L.dockWidth({ ...dock, open: false }, 1920), 0);
  assert.equal(L.dockWidth({ ...dock, mode: "float" }, 1920), 0);
  assert.equal(L.dockWidth(dock, 800), 0);                                // a phone: a sheet
  assert.equal(L.dockWidth(dock, 1440), 0);                               // under 1600px the page keeps its width and the panel floats
  assert.equal(L.shapeOf(dock, 1440), "float"); assert.equal(L.shapeOf(dock, 1600), "dock"); assert.equal(L.shapeOf(dock, 390), "sheet");
  assert.equal(L.dockWidth({ ...dock, w: 720 }, 1600), 720);
  assert.equal(L.dockWidth({ ...dock, w: 720 }, 1000), 0);
  const fl = { ...L.DEFAULT_LAYOUT, mode: "float", w: 400, h: 500, x: 100, y: 100 };
  const m = L.dragged(fl, -500, 9000, 1440, 900);
  assert.deepEqual([m.x, m.y], [0, 400]);
  const s = L.resized({ ...L.DEFAULT_LAYOUT, mode: "dock", w: 400 }, -100, 0, 1440, 900);
  assert.equal(s.w, 500);                                                 // dragged left: wider
  assert.equal(L.resized({ ...L.DEFAULT_LAYOUT, w: 400 }, 900, 0, 1440, 900).w, 300);
  const r = L.resized(fl, -50, -60, 1440, 900);
  assert.deepEqual([r.w, r.h, r.x, r.y], [450, 560, 50, 40]);             // the top-left corner moves, the bottom-right stays
});

// ---------- the live client ----------
test("a stream's events are read as they arrive, a half event waits", () => {
  const a = Live.parseSse('event: hello\ndata: {"live":["IN:X"]}\n\n: keep-alive\n\nevent: tick\ndata: [{"k":"IN:X","p":1}]\n\nevent: ti');
  assert.deepEqual(a.events.map((e) => e.event), ["hello", "tick"]);
  assert.equal(a.rest, "event: ti");
  assert.deepEqual(JSON.parse(a.events[1].data), [{ k: "IN:X", p: 1 }]);
  assert.deepEqual(Live.chunks([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// a client is always shut after its test, even one that failed: its timers would keep the run alive
const made = [];
const newClient = (t, o) => { const c = new Live.LiveClient(t, o); made.push(c); return c; };
afterEach(() => { made.splice(0).forEach((c) => c.destroy()); });
function sseResponse(text, hold = true) {
  const enc = new TextEncoder();
  let ctrl;
  const body = new ReadableStream({ start(c) { ctrl = c; c.enqueue(enc.encode(text)); if (!hold) c.close(); } });
  return { res: { body }, push: (t) => ctrl.enqueue(enc.encode(t)), end: () => ctrl.close() };
}

test("the live client joins every subscriber's keys, reads quotes, and streams ticks for the broker's instruments only", async () => {
  const calls = { open: [], quotes: [] };
  let feed;
  const t = {
    open: async (keys) => { calls.open.push(keys); feed = sseResponse('event: hello\ndata: {"live":["IN:AAA"],"poll":["US:BBB"]}\n\n'); return feed.res; },
    quotes: async (keys) => { calls.quotes.push(keys); return Object.fromEntries(keys.map((k) => [k, { price: 10, change: 1, change_pct: 1, prev_close: 9, at: "2026-10-23T10:15:00+05:30", currency: "INR", stale: false }])); },
  };
  const client = newClient(t, { pollMs: 40, debounceMs: 5, visible: () => true });
  const ticks = [], quotes = [];
  const a = client.subscribe({ tick: (k, x) => ticks.push([k, x.p]), quote: (k) => quotes.push(k) });
  const b = client.subscribe({});
  a.set(["IN:AAA", "US:BBB"]);
  b.set(["IN:AAA", "CRYPTO:BTC-USD"]);
  await sleep(120);
  assert.deepEqual(client.keys().sort(), ["CRYPTO:BTC-USD", "IN:AAA", "US:BBB"]);
  assert.deepEqual(calls.open, [["IN:AAA"]]);                                    // only the broker's feed is asked for, once, for everyone
  assert.ok(calls.quotes.length >= 2 && calls.quotes[0].length === 3);           // one read for all three keys
  assert.ok(quotes.includes("IN:AAA") && quotes.includes("US:BBB") && !quotes.includes("CRYPTO:BTC-USD"));      // each subscriber hears only its own
  assert.deepEqual(client.state().streamed, ["IN:AAA"]);
  // the quote of an instrument the stream doesn't carry moves its chart on every read; one the stream carries only until its first tick
  assert.ok(ticks.filter(([k]) => k === "US:BBB").length >= 2);
  assert.ok(ticks.filter(([k]) => k === "IN:AAA").length <= 1);
  feed.push('event: tick\ndata: [{"k":"IN:AAA","p":123.5,"v":900,"t":"2026-10-23T10:15:02+05:30"}]\n\n');
  await sleep(30);
  assert.deepEqual(ticks.filter(([k]) => k === "IN:AAA").pop(), ["IN:AAA", 123.5]);
  a.close(); b.close();
  await sleep(80);
  const seen = calls.quotes.length;
  await sleep(100);
  const idle = calls.quotes.length;
  client.destroy();
  assert.equal(idle, seen, "nothing is read with no subscriber");
});

test("a dropped stream is opened again after a pause while the reads carry on", async () => {
  let opens = 0;
  const t = {
    open: async () => { opens++; if (opens === 1) { const f = sseResponse('event: hello\ndata: {"live":["IN:AAA"]}\n\n', false); return f.res; } return sseResponse('event: hello\ndata: {"live":["IN:AAA"]}\n\n').res; },
    quotes: async (keys) => Object.fromEntries(keys.map((k) => [k, { price: 1, change: 0, change_pct: 0, prev_close: 1, at: null, currency: null, stale: false }])),
  };
  const client = newClient(t, { pollMs: 1000, debounceMs: 2, backoffMs: [20], visible: () => true });
  const s = client.subscribe({});
  s.set(["IN:AAA"]);
  await sleep(150);
  assert.ok(opens >= 2, `opened ${opens} times`);
  assert.deepEqual(client.state().streamed, ["IN:AAA"]);
  s.close();
  client.destroy();
});

test("a market that is shut or a login that is off is left to the reads, and looked at again in a minute", async () => {
  let opens = 0;
  const t = {
    open: async () => { opens++; return sseResponse('event: hello\ndata: {"live":[],"poll":["IN:AAA"],"reason":"closed"}\n\nevent: bye\ndata: {"reason":"poll"}\n\n', false).res; },
    quotes: async () => ({ "IN:AAA": { price: 5, change: 0, change_pct: 0, prev_close: 5, at: "2026-10-23T15:30:00+05:30", currency: "INR", stale: false } }),
  };
  const client = newClient(t, { pollMs: 30, debounceMs: 2, closedRetryMs: 60_000, visible: () => true });
  const ticks = [];
  const s = client.subscribe({ tick: (k, x) => ticks.push(x.p) });
  s.set(["IN:AAA"]);
  await sleep(150);
  assert.equal(opens, 1);                                  // not asked again every second
  assert.ok(ticks.length >= 2 && ticks[0] === 5);          // the reads move the chart meanwhile
  assert.equal(client.state().reason, "closed");
  s.close();
  client.destroy();
});

test("a page hidden for two minutes stops reading and starts again when it is back", async () => {
  let seen = true, reads = 0;
  const t = { open: async () => sseResponse('event: hello\ndata: {"live":[]}\n\n').res, quotes: async (k) => { reads++; return Object.fromEntries(k.map((x) => [x, null])); } };
  const client = newClient(t, { pollMs: 20, debounceMs: 2, idleMs: 60, visible: () => seen });
  const s = client.subscribe({});
  s.set(["US:AAA"]);
  await sleep(80);
  assert.ok(reads >= 2);
  seen = false;
  client.onVisible();                                      // the page is hidden: the idle clock starts
  await sleep(40);
  const mid = reads;
  await sleep(120);                                        // past idleMs: stopped
  const stopped = reads;
  await sleep(100);
  assert.equal(reads, stopped, `no reads while idle (${mid} → ${stopped})`);
  seen = true;
  client.onVisible();
  await sleep(80);
  assert.ok(reads > stopped, "reading again once the page is back");
  s.close();
  client.destroy();
});

// ---------- saved with the account ----------
test("drawings and the layout go through the account's JSON and come back the same", () => {
  const drawings = [
    { id: "a", kind: "trend", points: [{ t: 1_700_000_000_000, p: 100 }, { t: 1_710_000_000_000, p: 120.5 }], color: "blue", dash: "dashed" },
    { id: "b", kind: "fib", points: [{ t: 1_700_000_000_000, p: 200 }, { t: 1_700_500_000_000, p: 150 }] },
    { id: "c", kind: "hline", points: [{ t: 1_700_000_000_000, p: 99.9 }], color: "orange", locked: true },
    { id: "d", kind: "text", points: [{ t: 1_700_000_000_000, p: 101 }], text: "Gap fill" },
    { id: "e", kind: "measure", points: [{ t: 1_700_000_000_000, p: 90 }, { t: 1_700_900_000_000, p: 95 }] },
  ];
  const back = cleanDrawings(JSON.parse(JSON.stringify(drawings)));
  assert.equal(back.length, 5);
  for (const [i, d] of drawings.entries()) {
    assert.equal(back[i].id, d.id); assert.equal(back[i].kind, d.kind);
    assert.deepEqual(back[i].points, d.points);                       // time (ms) and price: they stay on their candle at every timeframe
    if (d.color) assert.equal(back[i].color, d.color);
    if (d.text) assert.equal(back[i].text, d.text);
  }
  const layout = { tf: "5m", range: "1M", type: "heikin", volume: false, studies: [{ id: "s1", type: "ema", params: [20], slot: 0 }, { id: "s2", type: "rsi", params: [14], slot: 1 }] };
  assert.deepEqual(cleanLayout(JSON.parse(JSON.stringify(layout))), layout);
  for (const tf of T.WORKSPACE_TFS) assert.equal(cleanLayout({ tf }).tf, tf, `${tf} is kept`);
  assert.equal(cleanLayout({ tf: "7m" }), null);
  assert.equal(cleanLayout({ tf: "2h", range: "nope", studies: "x" }).range, undefined);
});

// ---------- where the panel is drawn ----------
test("Market Watch is drawn once in the Shell, outside the page, and never inside the routes", () => {
  const shell = read("src/components/Shell.tsx");
  assert.equal([...shell.matchAll(/<MarketsLauncher/g)].length, 1);
  assert.match(shell, /<MarketsLauncher mode="app" userId=\{me\?\.id\} \/>/);
  const main = read("src/components/Shell.tsx");
  const routes = main.slice(main.indexOf("<main"), main.indexOf("</main>"));
  assert.doesNotMatch(routes, /MarketsLauncher/, "not inside the page, which changes with the route");
  assert.match(shell, /openMarkets\(\{ open: "toggle" \}\)/, "the phone's top bar has its button");
  const app = read("src/main.tsx");
  assert.match(app, /<Shell>/);
  assert.doesNotMatch(app.slice(app.indexOf("<Routes>"), app.indexOf("</Routes>")), /Shell|MarketsLauncher/);
  assert.match(app, /\/chart\/:market\/:symbol/);
});

test("the button holds no account code or chart: the panel and the chart load when it is opened", () => {
  const src = read("src/components/watch/Launcher.tsx");
  const imports = [...src.matchAll(/^import[^;]*?from\s+"([^"]+)"/gms)].map((m) => m[1]);
  for (const i of imports) assert.doesNotMatch(i, /(^|\/)lib\/(api|app)$|\/kit$|CompanySearch|charts\/price|WatchPanel|PublicBoard|watchApi|ChartWorkspace/, `Launcher imports ${i}`);
  assert.match(src, /import\("\.\/WatchPanel"\)/);
  assert.match(src, /import\("\.\/PublicBoard"\)/);
  const board = read("src/components/watch/PublicBoard.tsx");
  for (const i of [...board.matchAll(/^import[^;]*?from\s+"([^"]+)"/gms)].map((m) => m[1])) assert.doesNotMatch(i, /(^|\/)lib\/(api|app)$|^\.\/(api|app)$|\/kit$|watchApi|InstrumentSearch|WatchPanel/, `PublicBoard imports ${i}`);
  const ph = read("src/lib/watchLayout.ts"), pw = read("src/lib/watch.ts");
  for (const f of [ph, pw]) assert.doesNotMatch(f, /from "\.\/(api|app)"/);
  // the visitor half
  assert.match(read("src/visitor/VisitorApp.tsx"), /<PublicMarkets userId=\{userId\} \/>/);
  // a policy page is held to a download size (R5V-020): the visitor's first download has the button, and the launcher comes on the first press
  const pub = read("src/components/watch/PublicLauncher.tsx");
  assert.doesNotMatch(pub, /^import[^;]*from "\.\/Launcher"/m, "the launcher is not in a visitor's first download");
  assert.match(pub, /import\("\.\/Launcher"\)/);
  for (const i of [...pub.matchAll(/^import[^;]*?from\s+"([^"]+)"/gms)].map((m) => m[1])) assert.doesNotMatch(i, /watchLayout|(^|\/)lib\/(api|app)$|WatchPanel|PublicBoard/, `PublicLauncher imports ${i}`);
});

test("nothing on the panel or its words names a data source, and it gives no advice", () => {
  const files = ["WatchPanel", "WatchRow", "AddSymbol", "PublicBoard", "Launcher", "ChartWorkspace", "useWatch"].map((f) => read(`src/components/watch/${f}.${f === "useWatch" ? "ts" : "tsx"}`));
  files.push(read("src/pages/ChartPage.tsx"), read("src/lib/watch.ts"));
  const words = files.join("\n").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const strings = [...words.matchAll(/(["`])((?:\\.|(?!\1).)*)\1/g)].map((m) => m[2]).join("\n");
  assert.doesNotMatch(strings, /\b(yahoo|finnhub|screener|coinbase|kite|zerodha|nse india|tradingview)\b/i);
  assert.doesNotMatch(strings, /\b(buy|sell|hold|target price|should|recommend)\b/i);
});
