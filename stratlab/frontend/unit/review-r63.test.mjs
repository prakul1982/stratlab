// Round 63 (19 Oct 2026): India's open, live — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R63-001: on an expiry day the VIX card's IV says it is the next expiry's", async () => {
  const { vixIvNote } = await import("../src/lib/positioning.ts");
  const f = (v) => String(v);
  assert.match(vixIvNote(23150, "Live chain, 09:33", f, true), /The IV of the next expiry's options, as today's expire today\./);
  assert.match(vixIvNote(23150, "Live chain, 09:33", f), /The IV of the nearest expiry's options\./);
  assert.match(read("src/components/VixPanel.tsx"), /strike, !!ivNow\.rolled\)/);
});

test("R63-005: the PCR note names every recorded index in one sentence", async () => {
  const { pcrNote } = await import("../src/lib/positioning.ts");
  const at = (m) => `2026-10-19T03:${m}:00Z`;
  const rows = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX"].map((name, i) => ({ name, exchange: "NFO", source: "recorded", as_of: at(51 + (i % 2)) }));
  const note = pcrNote(rows);
  assert.equal((note.match(/newest recording/g) ?? []).length, 1, note);
  assert.match(note, /^NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX show StratLab's newest recordings, from .+ to .+\./);
  assert.match(pcrNote(rows.slice(0, 1)), /^NIFTY shows StratLab's newest recording, from /);
});

test("R63-002: prices on an open page are read again each minute while they're live", async () => {
  const { liveQuote, LIVE_REFRESH_MS } = await import("../src/lib/liveRefresh.ts");
  const now = Date.parse("2026-10-19T04:10:00Z");
  assert.equal(LIVE_REFRESH_MS, 60_000);
  assert.equal(liveQuote("2026-10-19T04:09:00Z", now), true);
  assert.equal(liveQuote("2026-10-16T10:00:00Z", now), false);
  assert.equal(liveQuote(null, now), false);
  const src = read("src/pages/Research.tsx");
  assert.match(src, /useLiveRefresh\(!!data\?\.indices\.some\(\(i\) => i\.live\)/);
  assert.match(src, /useLiveRefresh\(!!c\?\.market_open && \(c\.quote\?\.at == null \|\| liveQuote\(c\.quote\.at\)\)/);
  assert.match(src, /useLiveRefresh\(!!quotes && Object\.values\(quotes\)\.some\(\(q\) => liveQuote\(q\?\.at\)\)/);
});

test("R63-003, R63-008, R63-009: the watchlist fits a phone; breadth's range names what it moves; margin funding says its lag", () => {
  const src = read("src/pages/Research.tsx");
  assert.doesNotMatch(src, /header: "Flags"/);
  assert.match(src, /<span className="k-sub-line"><SurvBadges region=\{region\} symbol=\{w\.symbol\} \/>/);
  assert.match(read("src/pages/BreadthPage.tsx"), /<ChipBar label="History charts' range"/);
  assert.match(read("src/pages/MarginFundingPage.tsx"), /publishes each trading day's figures on the next trading day/);
});
