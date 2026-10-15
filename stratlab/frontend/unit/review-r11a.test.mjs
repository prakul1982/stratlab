// R11A: market clocks and the analytics pages' dates. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const { marketState, sessionFeed } = await import("../src/lib/marketHours.ts");

const US = { id: "US", tz: "America/New_York", status: "live", hours: { open: "09:30", close: "16:00", days: "Mon–Fri" }, holidays: [] };
const UK = { id: "UK", tz: "Europe/London", status: "live", hours: { open: "08:00", close: "16:30", days: "Mon–Fri" }, holidays: [] };
const EU = { id: "EU", tz: "Europe/Berlin", status: "live", hours: { open: "09:00", close: "17:30", days: "Mon–Fri" }, holidays: [] };

test("the next open across a weekend clock change is the exchange's opening time, not an hour off", () => {
  const us = marketState(US, new Date("2026-10-30T21:00:00Z"));       // Fri 17:00 ET; US clocks go back on Sun 1 Nov
  assert.equal(us.change.toISOString(), "2026-11-02T14:30:00.000Z");
  assert.match(sessionFeed({ feedConnected: true, lastTickAt: null, market: US, now: new Date("2026-10-30T21:00:00Z") }).text, /Mon 2 Nov, 09:30/);
  assert.equal(marketState(UK, new Date("2026-10-23T17:00:00Z")).change.toISOString(), "2026-10-26T08:00:00.000Z");
  assert.equal(marketState(EU, new Date("2026-10-23T17:00:00Z")).change.toISOString(), "2026-10-26T08:00:00.000Z");
  // and with no clock change in between it is as before
  assert.equal(marketState(US, new Date("2026-11-02T13:45:00Z")).change.toISOString(), "2026-11-02T14:30:00.000Z");
  assert.equal(marketState(US, new Date("2026-10-16T21:00:00Z")).change.toISOString(), "2026-10-19T13:30:00.000Z");
});

const { pcrNote, chainCounts } = await import("../src/lib/positioning.ts");
const { vixFreshness } = await import("../src/lib/vix.ts");
const { liveNoticeTone } = await import("../src/lib/breadthLive.ts");

test("an index shown from a recording older than the close says that recording's date, not 'its last close'", () => {
  const old = { name: "BANKNIFTY", exchange: "NFO", source: "recorded", at_close: false, as_of: "2026-10-09T15:25+05:30" };
  const close = { name: "NIFTY", exchange: "NFO", source: "recorded", at_close: true, as_of: "2026-10-15T15:25+05:30" };
  const both = pcrNote([close, old]);
  assert.match(both, /the other indices show StratLab's recording of its last close/);
  assert.match(both, /BANKNIFTY shows StratLab's newest recording, from Fri,? 9 Oct, 15:25 IST\./);
  const alone = pcrNote([old]);
  assert.doesNotMatch(alone, /last close/);
  assert.match(alone, /9 Oct, 15:25 IST/);
  assert.match(pcrNote([close]), /^The market is shut, so each index shows StratLab's recording of its last close\./);
});

test("India VIX from a stored close is dated 'Close on <day>' with the stale badge", () => {
  const f = vixFreshness({ quote: null, value_day: "2026-10-09", intraday: [], today: "2026-10-15" });
  assert.equal(f.stale, true);
  assert.match(f.stamp, /^Close on Fri,? 9 Oct$/);
  assert.match(f.rangeLabel, /^Range on Fri,? 9 Oct$/);
  const q = vixFreshness({ quote: { as_of: "2026-10-15T06:34:00Z" }, value_day: null, intraday: [], today: "2026-10-15" });
  assert.equal(q.stamp, "As of 15 Oct, 12:04 IST");
  assert.equal(vixFreshness({ quote: null, intraday: [], today: "2026-10-15" }).stamp, null);
});

test("the chain panel says which strikes each figure counts", () => {
  const rows = Array.from({ length: 41 }, (_, i) => ({ strike: 24000 + 50 * i }));
  const t = chainCounts({ near_strikes: 15, window_strikes: 31, strikes_counted: 61, rows });
  assert.equal(t.maxPain, "over the 31 strikes around the money, as the PCR");
  assert.match(t.note, /PCR and max pain count the 31 strikes around the money \(15 either side/);
  assert.match(t.note, /most call and put open interest are over all 61 strikes read; the chart shows the 41 nearest\./);
});

test("live breadth before the first count is a plain notice, an outage a warning", () => {
  assert.equal(liveNoticeTone({ state: "pending" }), "info");
  assert.equal(liveNoticeTone({ state: "unavailable" }), "warn");
});
