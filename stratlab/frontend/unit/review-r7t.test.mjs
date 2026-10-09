// Round 7 time review of the live site during India's open (9 Oct 2026): the app's side, each on the reviewer's example.
// Every clock here is a fixed instant with its zone. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
// the app's modules read the page's config and storage when they load: an empty page here
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("R7T-001: a 52-week range from another class of shares is never drawn under the price", async () => {
  const { plausibleRange } = await import("../src/lib/research.ts");
  assert.equal(plausibleRange(511.05, 698000, 806102.8), false);       // Class A's range beside BRK-B's price
  assert.equal(plausibleRange(511.05, 464.01, 537.74), true);
  assert.equal(plausibleRange(1162.1, 1160.2, 1550), true);
  assert.match(read("src/components/Research.tsx"), /!plausibleRange\(px, low, high\)\) return null/);
});

test("R7T-002: the option chain counts contracts (lots), and says so", async () => {
  const { chainUnit, unitLine } = await import("../src/lib/positioning.ts");
  assert.equal(chainUnit({ unit: "lots" }), "contracts");
  assert.equal(chainUnit({ unit: "shares" }), "shares");
  assert.match(unitLine({ unit: "lots", lot: 65 }), /contracts \(lots of 65 shares\)/);
  assert.match(unitLine({ unit: "shares", lot: null }), /in shares/);
  const page = read("src/pages/PositioningPage.tsx");
  assert.doesNotMatch(page, /oi\)\} contracts`/);                     // no count called contracts whatever its unit
  assert.match(read("src/components/StrikeChart.tsx"), /\{contractsShort\(max\)\} \{unit\}/);
});

test("R7T-003: an index at a previous session's level is never 'today'; Mine's tiles say their day", async () => {
  const { indexWhen } = await import("../src/lib/research.ts");
  const day = (d) => ({ "2026-10-08": "8 Oct", "2026-10-09": "9 Oct" }[d]);
  assert.equal(indexWhen({ day: "2026-10-08", live: false, stale: true }, day), "8 Oct close · not updated today yet");
  assert.equal(indexWhen({ day: "2026-10-09", live: true, stale: false }, day), "today");
  assert.equal(indexWhen({ day: "2026-10-08", live: false, stale: false }, day), "on 8 Oct");
  assert.equal(indexWhen({}, day), "today");                          // an older server's answer reads as before
  const { tileWhen, tileToday, MARKET_TILES } = await import("../src/lib/mine.ts");
  assert.equal(tileWhen("2026-10-08", "2026-10-09", day), "on 8 Oct");
  assert.equal(tileWhen("2026-10-09", "2026-10-09", day), null);
  const sensex = MARKET_TILES.find((t) => t.id === "sensex");
  assert.equal(tileToday(sensex, new Date("2026-10-08T20:00:00Z")), "2026-10-09");       // 01:30 IST on 9 Oct
  const sp = MARKET_TILES.find((t) => t.id === "sp500");
  assert.equal(tileToday(sp, new Date("2026-10-09T03:00:00Z")), "2026-10-08");            // 23:00 in New York on 8 Oct
  const { aiReason } = await import("../src/components/Research.tsx").catch(() => ({ aiReason: null }));
  if (aiReason) assert.match(aiReason("SENSEX hasn't updated for today's session yet. Ask again in a minute."), /SENSEX hasn't updated/);
  assert.match(read("src/components/Research.tsx"), /hasn't updated\|haven't updated/);
});

test("R7T-004: before 09:15 IST the price is the pre-open's, never the last close", async () => {
  const { priceLabel } = await import("../src/lib/research.ts");
  assert.deepEqual(priceLabel({ market_open: false, phase: "pre_open" }), { label: "Pre-open (indicative)", since: "against the last close" });
  assert.deepEqual(priceLabel({ market_open: false, phase: null }), { label: "Last close", since: "on the day" });
  assert.deepEqual(priceLabel({ market_open: true }), { label: null, since: "today" });
  assert.match(read("src/pages/Research.tsx"), /preOpen=\{c\.phase === "pre_open"\}/);
});

test("R7T-005: the PCR is one figure across the table, the chain panel and the history", async () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.doesNotMatch(page, /header: "Near the money"/);
  assert.match(page, /header: "All strikes read"/);
  const { NEAR_STRIKES } = await import("../src/lib/positioning.ts");
  assert.equal(NEAR_STRIKES, 15);
});

test("R7T-010: the home breadth card shows the live point while the market trades, else says last close", async () => {
  const { cardFigures } = await import("../src/lib/breadth.ts");
  const fig = (v) => ({ value: v, prev: null, change: null });
  const today = { day: "2026-10-08", prev_day: "2026-10-07", adv: fig(18), dec: fig(232), pct50: fig(20), highs: fig(1), lows: fig(30) };
  const live = { state: "live", as_of: "09:30", latest: { adv: 136, dec: 108, unch: 1, pct50: 48.2 } };
  const on = cardFigures({ today, live });
  assert.equal(on.live, true);
  assert.equal(on.adv, 136);
  assert.equal(on.dec, 108);
  assert.equal(on.when, "Live as of 09:30 IST");
  const off = cardFigures({ today, live: null });
  assert.equal(off.live, false);
  assert.equal(off.adv, 18);
  assert.match(off.when, /^Last close, 8 Oct/);
  assert.equal(cardFigures({ today, live: { state: "unavailable", latest: null } }).live, false);
});

test("R7T-011: an options session's id at /paper opens its own page, and a crash isn't a download message", async () => {
  const { sessionPath } = await import("../src/lib/tradeUi.ts");
  assert.equal(sessionPath({ id: "610500be", kind: "options" }), "/options/s/610500be");
  assert.equal(sessionPath({ id: "610500be", instrument: { type: "OPTIONS" } }), "/options/s/610500be");
  assert.equal(sessionPath({ id: "s1", instrument: { signal: true } }), "/trade/signals/s1");
  assert.equal(sessionPath({ id: "s2", instrument: { type: "EQ" } }), "/paper/s2");
  const paper = read("src/pages/PaperPage.tsx");
  assert.match(paper, /bars: s\.bars \?\? \[\], events: s\.events \?\? \[\], equity_curve: s\.equity_curve \?\? \[\]/);
  const guard = read("src/components/LoadGuard.tsx");
  assert.match(guard, /failed: isLoadError\(error\) \? "load" : "crash"/);
  assert.match(guard, /This page ran into a problem/);
  assert.match(read("src/main.tsx"), /<PageBoundary at=\{loc\.pathname\}>/);
  const { isLoadError } = await import("../src/components/LoadGuard.tsx").catch(() => ({ isLoadError: null }));
  if (isLoadError) {
    assert.equal(isLoadError(new TypeError("Cannot read properties of undefined (reading 'length')")), false);
    assert.equal(isLoadError(new TypeError("Failed to fetch dynamically imported module: /assets/PaperPage-x.js")), true);
  }
});

test("R7T-012: Admin's live price feed counts options paper sessions as running", async () => {
  const { feedTile } = await import("../src/pages/admin/attention.ts");
  const sv = (o) => ({ feed_connected: false, live_sessions: 1, india_sessions: 0, options_sessions: 0, ...o });
  const t = feedTile(sv({ options_sessions: 1 }));
  assert.equal(t.state, "ok");
  assert.equal(t.detail, "Not needed: 1 options paper session running on quotes read every few seconds");
  assert.equal(feedTile(sv({})).detail, "Idle: no India paper sessions running");
  assert.match(feedTile(sv({ feed_connected: true, india_sessions: 2, options_sessions: 1 })).detail, /^Connected, 2 India paper sessions running · 1 options paper session/);
});

test("R7T-013: after a stop-out the session says when the next entry may come", async () => {
  const { gapLine } = await import("../src/lib/options.ts");
  const now = new Date("2026-10-09T04:15:00Z");                       // 09:45 IST, four minutes after the 09:41 stop
  assert.equal(gapLine({ cool_until: "2026-10-09T11:41:00+05:30", next_entry: "11:41" }, 120, "14:45", "09:30", now),
    "Next entry from 11:41: entries are 120 min apart.");
  assert.match(gapLine({ cool_until: "2026-10-09T15:00:00+05:30", next_entry: null }, 120, "14:45", "09:30", now), /next market day/);
  assert.equal(gapLine({ cool_until: "2026-10-09T09:00:00+05:30", next_entry: "09:00" }, 120, "14:45", "09:30", now), null);   // gap over
  assert.equal(gapLine({}, 120, "14:45", "09:30", now), null);
  assert.match(read("src/pages/OptionsSession.tsx"), /gapLine\(a, s\.timing\.cooldown/);
});

test("R7T-014: size changes are handled a frame later, never inside the observer (Safari's ResizeObserver loop error)", () => {
  for (const f of ["src/components/StrikeChart.tsx", "src/components/Rotation.tsx", "src/components/chart/core.ts", "src/components/Shell.tsx"]) {
    const src = read(f);
    assert.match(src, /watchSize\(/, f);
    assert.doesNotMatch(src, /new ResizeObserver\(/, f);
  }
  assert.match(read("src/charts/price/engine.ts"), /this\.sizeFrame = requestAnimationFrame\(\(\) => this\.resize\(\)\)/);
  assert.match(read("src/lib/resize.ts"), /frame = raf\(/);
});
