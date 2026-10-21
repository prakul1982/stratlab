// Round 72 (19 Oct 2026): the US close and the US brief — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R72-001: a just-closed US tile says its closing prints are settling, not 'on 19 Oct'", async () => {
  const { tileWhen } = await import("../src/lib/mine.ts");
  const day = (d) => d.slice(8) + " Oct";
  assert.equal(tileWhen("2026-10-19", "2026-10-19", day, true, true, true), "today, closing prints settling");
  assert.equal(tileWhen("2026-10-19", "2026-10-19", day, true, true, false), "on 19 Oct");
  const { minutesSinceClose } = await import("../src/lib/marketHours.ts");
  const us = { id: "US", tz: "America/New_York", hours: { open: "09:30", close: "16:00", days: "Mon–Fri" }, holidays: [] };
  assert.equal(minutesSinceClose(us, new Date("2026-10-19T20:06:00Z")), 6);
  assert.equal(minutesSinceClose(us, new Date("2026-10-19T19:58:00Z")), null);        // still open
  assert.match(read("src/pages/MineHome.tsx"), /settling\(tileMarket\(t\)\)[,)]/);
});

test("R72-005: the Invest home's India 'Coming up' keeps the exchange holiday", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /e\.kind !== "expiry" && \(region !== "US" \|\| e\.kind === "us"\)/);
});
