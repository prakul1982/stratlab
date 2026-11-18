// Lane fix17 (LIVE13B review of Release 71): the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE13B-003: 'Coming up' keeps the monthly F&O expiry of the week, as /calendar lists it", async () => {
  const { comingMarketEvents } = await import("../src/lib/eventTime.ts");
  const ev = (id, kind, date, title, time = "15:30") => ({ id, kind, date, time, title, detail: "", figure: null, previous: null, url: null, status: "scheduled" });
  // Wed 18 Nov 2026: SENSEX weekly Thu 19, the monthly moved to Mon 23 (Tue 24 a holiday), the next SENSEX weekly Thu 26
  const events = [ev("sx", "expiry", "2026-11-19", "SENSEX weekly expiry"), ev("m", "expiry", "2026-11-23", "Monthly F&O expiry"),
    ev("h", "holiday", "2026-11-24", "Exchange holiday", null), ev("sx2", "expiry", "2026-11-26", "SENSEX monthly expiry"),
    ev("m2", "expiry", "2026-12-29", "Monthly F&O expiry")];
  const o = { today: "2026-11-18", nowHm: "14:16", end: "2026-12-18", weekEnd: "2026-11-25" };
  assert.deepEqual(comingMarketEvents(events, o).map((e) => e.id), ["sx", "m", "h"]);
  // once the week moves on, the next month's is the nearest of its name
  assert.deepEqual(comingMarketEvents(events, { ...o, today: "2026-11-24", weekEnd: "2026-12-01" }).map((e) => e.id), ["h", "sx2"]);
  assert.deepEqual(comingMarketEvents(events, { ...o, region: "US" }).map((e) => e.id), []);
});
