// Round 77 (21 Oct 2026): India after the close, the first trading day after the 20 Oct holiday — the frontend side.
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
const { tileWhen } = await import("../src/lib/mine.ts");
const { sectorColumnLabel } = await import("../src/lib/breadthLive.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const dayText = (iso) => `${Number(iso.slice(8))} Oct`;

test("breadth compares with the previous close, never 'yesterday's' after a holiday (R77-001)", () => {
  const page = read("src/pages/BreadthPage.tsx");
  assert.doesNotMatch(page, /yesterday's close/);
  assert.match(page, /unchanged · against the previous close/);
});

test("the sector table's newest column is the latest stored day, not 'Today' (R77-002)", () => {
  assert.equal(sectorColumnLabel({ label: "Today", day: "2026-10-19" }, dayText), "Latest · 19 Oct");
});

test("USD/INR and Gold say 'today' beside the indices' labels (R77-006)", () => {
  assert.equal(tileWhen("2026-10-21", "2026-10-21", dayText, false, false, false, true), "today");
  assert.equal(tileWhen("2026-10-20", "2026-10-21", dayText, false, false, false, true), "on 20 Oct");
  assert.equal(tileWhen("2026-10-21", "2026-10-21", dayText, false, true), "today, live");
  assert.equal(tileWhen("2026-10-21", "2026-10-21", dayText), null);
  assert.match(read("src/pages/MineHome.tsx"), /settling\(tileMarket\(t\)\), !tileMarket\(t\)\)/);
});

test("a paper fall that held to the close is said once (R77-007)", () => {
  const src = read("src/components/RiskOverview.tsx");
  assert.match(src, /c\.deepest_fall\.day_close === c\.deepest_fall\.pnl/);
  assert.match(src, /and held to the close`/);
});
