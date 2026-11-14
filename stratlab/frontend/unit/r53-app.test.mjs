// Release 53, lane app53: whole-app fixes from the LIVE8A / LIVE8B reviews (frontend side).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE8B-002: a business-update chart puts each point at its month, so unread months are a stretch of the axis", async () => {
  const { monthIndex, monthOf, periodName } = await import("../src/lib/biz.ts");
  assert.equal(monthIndex("2026-06") - monthIndex("2025-10"), 8);       // Oct 2025 → Jun 2026 is eight months, not one step
  assert.equal(monthOf(monthIndex("2026-10")), "2026-10");
  assert.equal(monthOf(monthIndex("2026-01")), "2026-01");
  assert.ok(Number.isNaN(monthIndex("junk")));
  assert.equal(periodName(monthOf(monthIndex("2025-12"))), "Dec 2025");
  const chart = read("src/components/BizUpdates.tsx");
  assert.match(chart, /x: xs, xFormat/);
});
