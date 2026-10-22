// Round 79 (22 Oct 2026): India's open — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const { pcrNote } = await import("../src/lib/positioning.ts");
const { moverDay } = await import("../src/lib/mine.ts");
const { breadthChipLabel } = await import("../src/lib/breadthLive.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("during the session a recording stands in for a live chain, and says why (R79-001)", () => {
  const rec = ["NIFTY", "SENSEX"].map((name) => ({ name, exchange: "NFO", source: "recorded", as_of: "2026-10-22T04:16:00Z" }));
  const note = pcrNote(rec);
  assert.match(note, /^NIFTY and SENSEX show StratLab's newest recordings, from .+\. The live chain couldn't be read just then; it is tried again each minute\.$/);
  assert.doesNotMatch(note, /at most once a minute/);
  assert.equal(pcrNote([{ name: "NIFTY", exchange: "NFO", source: "live" }]), "Live chains are read at most once a minute.");
});

test("India VIX says when its range holds ticks the chart doesn't draw (R79-002)", () => {
  assert.match(read("src/components/VixPanel.tsx"), /q\?\.range_off_line \? "The exchange's range includes ticks the chart below doesn't draw"/);
});

test("positioning changes are from the previous trading day, not 'the day before' (R79-003)", () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.doesNotMatch(page, /> from the day before</);
  assert.equal((page.match(/from the previous trading day</g) ?? []).length, 2);
});

test("a watchlist move that isn't today's names its day (R79-005)", () => {
  const now = new Date("2026-10-22T04:21:00Z");                 // 09:51 IST; New York 00:21 on 22 Oct
  assert.equal(moverDay("US", { at: "2026-10-21T20:00:00Z" }, now), "2026-10-21");
  assert.equal(moverDay("IN", { at: "2026-10-22T04:20:00Z" }, now), null);
  assert.equal(moverDay("IN", { change_day: "2026-10-21", at: "2026-10-21T10:00:00Z" }, now), "2026-10-21");
  assert.equal(moverDay("US", { at: null }, now), null);
});

test("the breadth chip names the daily figures above a live card (R79-008)", () => {
  assert.equal(breadthChipLabel({ state: "live" }), "Daily figures to");
  assert.equal(breadthChipLabel({ state: "final" }), "Daily figures to");
  assert.equal(breadthChipLabel(null), "Prices as of");
});
