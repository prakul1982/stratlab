// LIVE-1: every page that shows live market numbers reads them again by itself, at least each minute, while its market trades
// and the tab is in view. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const mk = (id, tz, open, close, extra = {}) => ({ id, name: id, venues: "", currency: "INR", symbol: "₹", tz, hours: open ? { open, close, days: "Mon–Fri" } : { open: null, close: null, days: "24 hours" },
  what: "", costs: "", brokerage: 0, status: "live", max_days: null, holidays: [], ...extra });
const MARKETS = [mk("IN", "Asia/Kolkata", "09:15", "15:30"), mk("US", "America/New_York", "09:30", "16:00"), mk("CRYPTO", "UTC", null, null),
  mk("FX", "UTC", null, null), mk("CMDTY", "America/New_York", null, null), mk("MCX", "Asia/Kolkata", "09:00", "23:55")];
const at = (iso) => Date.parse(iso);

test("LIVE-1: a market is live while it trades and for a quarter hour after (the US for its settling time), never when shut", async () => {
  const { marketsLive, LIVE_GRACE_MIN } = await import("../src/lib/liveRefresh.ts");
  assert.equal(LIVE_GRACE_MIN, 15);
  // Wednesday 28 Oct 2026: India 09:15-15:30 IST (03:45-10:00 UTC), the US 09:30-16:00 EDT (13:30-20:00 UTC)
  assert.equal(marketsLive(MARKETS, ["IN"], at("2026-10-28T04:30:00Z")), true);       // 10:00 IST
  assert.equal(marketsLive(MARKETS, ["IN"], at("2026-10-28T03:30:00Z")), false);      // 09:00 IST: before the open
  assert.equal(marketsLive(MARKETS, ["IN"], at("2026-10-28T10:10:00Z")), true);       // 15:40 IST: the closing prints
  assert.equal(marketsLive(MARKETS, ["IN"], at("2026-10-28T10:20:00Z")), false);      // 15:50 IST: shut for 20 minutes
  assert.equal(marketsLive(MARKETS, ["US"], at("2026-10-28T14:00:00Z")), true);
  assert.equal(marketsLive(MARKETS, ["US"], at("2026-10-28T20:40:00Z")), true);       // 40 minutes after the US close: still settling
  assert.equal(marketsLive(MARKETS, ["US"], at("2026-10-28T21:00:00Z")), false);      // 60 minutes after
  assert.equal(marketsLive(MARKETS, ["IN"], at("2026-10-28T14:00:00Z")), false);      // India's evening
  // the weekend: India, the US and the dollar are shut; crypto never is
  const sat = at("2026-10-31T06:00:00Z");
  assert.equal(marketsLive(MARKETS, ["IN", "US", "FX", "CMDTY"], sat), false);
  assert.equal(marketsLive(MARKETS, ["CRYPTO"], sat), true);
  // the dollar and gold trade round the clock on a weekday, from Sunday evening to Friday evening New York time
  assert.equal(marketsLive(MARKETS, ["FX"], at("2026-10-28T22:00:00Z")), true);
  assert.equal(marketsLive(MARKETS, ["CMDTY"], at("2026-10-28T22:00:00Z")), true);
  assert.equal(marketsLive(MARKETS, ["FX"], at("2026-10-30T22:30:00Z")), false);      // Friday 18:30 New York
  // any one of several
  assert.equal(marketsLive(MARKETS, ["IN", "US"], at("2026-10-28T14:00:00Z")), true);
});

test("LIVE-1: a holiday is shut, a feed marked offline at sign-in still counts by its hours, an unknown or coming-soon market never does", async () => {
  const { marketsLive } = await import("../src/lib/liveRefresh.ts");
  const holiday = MARKETS.map((m) => (m.id === "IN" ? { ...m, holidays: ["2026-10-28"] } : m));
  assert.equal(marketsLive(holiday, ["IN"], at("2026-10-28T04:30:00Z")), false);
  // the list is read once at sign-in: a feed that was off then may be on at the open, and a page left open must read then
  const offline = MARKETS.map((m) => (m.id === "IN" ? { ...m, status: "offline" } : m));
  assert.equal(marketsLive(offline, ["IN"], at("2026-10-28T04:30:00Z")), true);
  const soon = MARKETS.map((m) => (m.id === "IN" ? { ...m, status: "soon" } : m));
  assert.equal(marketsLive(soon, ["IN"], at("2026-10-28T04:30:00Z")), false);
  assert.equal(marketsLive(MARKETS, ["XX"], at("2026-10-28T04:30:00Z")), false);
  assert.equal(marketsLive([], ["IN"], at("2026-10-28T04:30:00Z")), false);          // the list not read yet
  assert.equal(marketsLive(MARKETS, [], at("2026-10-28T04:30:00Z")), false);
});

test("LIVE-1: the refresh is a minute, and My space's levels are kept under a minute while a market trades", async () => {
  const { LIVE_REFRESH_MS } = await import("../src/lib/liveRefresh.ts");
  const { SERIES_KEEP_MS, SERIES_LIVE_KEEP_MS, STRIP_MARKETS, MARKET_TILES } = await import("../src/lib/mine.ts");
  assert.equal(LIVE_REFRESH_MS, 60_000);
  assert.ok(SERIES_LIVE_KEEP_MS < LIVE_REFRESH_MS, "a tick one minute after the last read must read again, not reuse it");
  assert.ok(SERIES_KEEP_MS > LIVE_REFRESH_MS, "with the market shut the candles are reused");
  // every tile's market is one the strip watches: the indices (India, the US), the dollar (FX) and gold (global commodities)
  assert.deepEqual([...STRIP_MARKETS].sort(), ["CMDTY", "FX", "IN", "US"]);
  for (const t of MARKET_TILES) {
    const m = "research" in t.from ? t.from.research[0] : t.from.instrument.startsWith("FX:") ? "FX" : "CMDTY";
    assert.ok(STRIP_MARKETS.includes(m), t.id);
  }
});

test("LIVE-1: My space's tiles, P&L, watchlist and net worth read again on the markets' clock; the markets card says when", () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.match(mine, /const live = useMarketsLive\(STRIP_MARKETS\);\s+const series = useMarketStrip\(later, live\);/);
  assert.match(mine, /useLiveRefresh\(later && live, \(\) => \{ api<IndiaGold>\("\/money\/gold"\)/);          // gold in rupees too
  assert.match(mine, /data-testid="mine-mkt-at">Levels read at \{fmtTime\(readAt, \{ tz: IST, zone: true \}\)\}, and again each minute while a market is open\./);
  // the P&L card: holdings again while India or the US trades; the net worth card: the priced part only
  assert.match(mine, /const live = useMarketsLive\(\["IN", "US"\]\);\s+useLiveRefresh\(live && h !== null && h !== "none" && h\.rows\.length > 0, \(\) => \{ api<Holdings>\("\/holdings"\)/);
  assert.match(mine, /api<Partial<NwView>>\("\/money\/net-worth\?live=true"\)/);
  assert.match(mine, /useMarketsLive\(v !== null && v !== "none" \? pricedMarkets\(v\.assets/);
  // the watchlist movers: the quotes again, keeping the rows when a read finds none
  assert.match(mine, /const trading = useMarketsLive\(\["IN", "US"\]\);\s+useLiveRefresh\(trading && !!items\?\.length && movers !== null/);
  const lib = read("src/lib/mine.ts");
  assert.match(lib, /useLiveRefresh\(enabled && live, \(\) => \{/);
  assert.match(lib, /if \(on\.current && s\) setOut/);                                  // a failed read changes nothing
});

test("LIVE-1: the net worth's live part is laid over the page; the history, deposit tax and limits stay; the markets are those it is priced in", async () => {
  const { mergeLiveNetWorth, pricedMarkets } = await import("../src/lib/networth.ts");
  const cur = { as_of: "2026-10-27", totals: { net: 100 }, assets: [{ id: "a" }], history: [{ d: "2026-10-01", net: 90 }], history_allowed: true, history_count: 1, deposit_tax: { x: 1 }, limit: 5, count: 3, valuation: 2 };
  const got = mergeLiveNetWorth(cur, { as_of: "2026-10-28", totals: { net: 120 }, assets: [{ id: "a" }, { id: "b" }], history: null, deposit_tax: null, limit: null });
  assert.equal(got.totals.net, 120);
  assert.equal(got.assets.length, 2);
  assert.equal(got.as_of, "2026-10-28");
  assert.deepEqual(got.history, cur.history);
  assert.deepEqual(got.deposit_tax, { x: 1 });
  assert.equal(got.limit, 5);
  assert.equal(got.valuation, 2);
  assert.equal(mergeLiveNetWorth(cur, {}), cur);                                       // a reply without totals changes nothing
  assert.equal(mergeLiveNetWorth(cur, null), cur);
  const rows = [{ kind: "stocks_in", basis: "market price" }, { kind: "stocks_us", basis: "at cost" }, { kind: "gold", basis: "market price" }, { kind: "fd", basis: "formula" },
    { kind: "crypto", basis: "market price" }, { kind: "sgb", basis: "market price" }];
  assert.deepEqual(pricedMarkets(rows).sort(), ["CRYPTO", "IN", "MCX"]);                // a US line at cost moves with no tick
  assert.deepEqual(pricedMarkets([{ kind: "fd", basis: "formula" }, { kind: "ppf", basis: "formula" }]), []);
  assert.deepEqual(pricedMarkets(undefined), []);
});

test("LIVE-1: breadth's live card is laid over the page for its own group only", async () => {
  const { withLive } = await import("../src/lib/breadth.ts");
  const cur = { group: { id: "nifty500" }, today: { day: "2026-10-27" }, live: { state: "live", as_of: "10:00" }, pending: undefined, history: { days: ["a"] } };
  const next = withLive(cur, { live: { state: "live", as_of: "10:15" }, pending: { day: "2026-10-28" } }, "nifty500");
  assert.equal(next.live.as_of, "10:15");
  assert.deepEqual(next.history, cur.history);
  assert.equal(withLive(cur, { live: { as_of: "10:15" } }, "sp500"), cur);              // another group's answer is never laid over this one
  assert.equal(withLive(null, { live: null }, "nifty500"), null);
  assert.equal(withLive("error", { live: null }, "nifty500"), "error");
  assert.equal(withLive(cur, null, "nifty500"), cur);
  assert.equal(withLive(cur, { live: null }, "nifty500").live, null);                    // the live card ends when the server says so
});

test("LIVE-1: each page with live numbers reads them again on a clock", () => {
  const wired = (file, ...res) => { const src = read(file); for (const re of res) assert.match(src, re, `${file}: ${re}`); };
  wired("src/pages/SpaceHomes.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{ api<VixBrief>\("\/trade\/vix"\)/, /useMarketRefresh\(\["IN", "US"\], \(\) => \{ api<Holdings>\("\/holdings"\)/);
  wired("src/components/Research.tsx", /useLiveRefresh\(!!q && Object\.values\(q\)\.some\(\(x\) => liveQuote\(x\?\.at\)\)/);          // the Invest home's watchlist tiles and similar companies
  wired("src/components/BreadthCard.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{[\s\S]*breadthApi\.live\(group\)/);
  wired("src/pages/BreadthPage.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{[\s\S]*breadthApi\.live\(g\)/);
  wired("src/pages/HoldingsPage.tsx", /useMarketRefresh\(\["IN", "US"\], \(\) => \{[\s\S]*api<View>\("\/holdings"\)\.then\(\(v\) => \{ if \(n === readSeq\.current\) setView\(v\)/);
  wired("src/pages/money/NetWorthPage.tsx", /useMarketRefresh\(pricedMarkets\(view\?\.assets\)/, /"\/money\/net-worth\?live=true"/);
  wired("src/pages/InvestorHome.tsx", /useMarketRefresh\(\[region\], \(\) => \{[\s\S]*quotesInBatches/);
  wired("src/pages/Research.tsx", /useLiveRefresh\(!!res && \[res\.a, res\.b\]\.some/);                                                   // the compare page
  wired("src/pages/PositioningPage.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{ api<\{ pcr: PcrRow\[\] \}>/, /useMarketRefresh\(\["IN"\], \(\) => \{\s+api<ChainFacts>/);
  wired("src/components/VixPanel.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{ api<Vix>\("\/trade\/vix"\)/);
  wired("src/pages/OptionsPage.tsx", /useMarketRefresh\(\[s\.exchange === "NFO" \|\| s\.exchange === "BFO" \? "IN" : s\.exchange\]/);
  wired("src/pages/EtfGapsPage.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{ void loadEtfGaps\(true\)/);
  wired("src/components/EtfGap.tsx", /useMarketRefresh\(\["IN"\], \(\) => \{ etfGapApi\.detail\(symbol\)/);
  wired("src/pages/trade/ClosingAuctionPage.tsx", /const PREOPEN_MS = 60_000;/);
  wired("src/lib/app.tsx", /useLiveRefresh\(!!session, \(\) => \{\s+api<Market\[\]>\("\/markets"\)/);
  // the IPO pages: each minute while bidding is open (was two)
  for (const f of ["src/pages/IpoPage.tsx", "src/pages/IposPage.tsx"]) { assert.doesNotMatch(read(f), /120_000/, f); assert.match(read(f), /useLiveRefresh\(.*load\(true\)\)/, f); }
});

test("LIVE-1: nothing the refresh reads again is an upload or tax work; the holdings page keeps its facts and actions", () => {
  const h = read("src/pages/HoldingsPage.tsx");
  const from = h.indexOf('useMarketRefresh(["IN", "US"]');
  const live = h.slice(from, h.indexOf("}, !!view", from));
  assert.ok(live.length > 50);
  assert.doesNotMatch(live, /loadFacts|setActionsAt|\/tax|\/import|show\(/);
  assert.match(h, /const put = useCallback\(\(v: View\) => \{ readSeq\.current\+\+; setView\(v\); \}, \[\]\);/);      // an edit's answer is never overwritten by an older price read
  const nw = read("src/pages/money/NetWorthPage.tsx");
  assert.match(nw, /readSeq\.current\+\+;\s+setView\(got\);/);
});
