// Market page fixes: a custom range starts from India's date. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

test("a custom range's first day is India's date, a day ahead of UTC between 00:00 and 05:30 IST", async () => {
  const { rangeFrom } = await import("../src/lib/positioning.ts");
  assert.equal(rangeFrom(30, Date.parse("2026-10-14T20:00:00Z")), "2026-09-15");     // 01:30 IST on the 15th
  assert.equal(rangeFrom(30, Date.parse("2026-10-14T10:00:00Z")), "2026-09-14");
});
