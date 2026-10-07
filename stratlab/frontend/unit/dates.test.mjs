// A date written as 2025-03-10 is a calendar day: it reads the same wherever the reader is. (new Date("2025-03-10") is
// midnight UTC, which a reader in the US saw as 9 Mar: the wrong day on a tax report's bought and sold dates.)
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

process.env.TZ = "America/Los_Angeles";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { dateOnly, asDate } = await import("../src/lib/format.ts");

test("a date without a time reads as that day for a reader west of Greenwich", () => {
  assert.equal(dateOnly("2025-03-10"), "10 Mar 2025");
  assert.equal(dateOnly("2026-04-01"), "1 Apr 2026");
  assert.equal(dateOnly("2024-02-29"), "29 Feb 2024");
  const d = asDate("2025-12-31");
  assert.deepEqual([d.getFullYear(), d.getMonth(), d.getDate()], [2025, 11, 31]);
});

test("a moment keeps being a moment", () => {
  assert.equal(dateOnly("2025-03-10T20:00:00Z"), "10 Mar 2025");
  assert.equal(asDate("2025-03-10T20:00:00Z").getTime(), Date.parse("2025-03-10T20:00:00Z"));
  assert.equal(dateOnly(null), "–");
  assert.equal(dateOnly(""), "–");
});
