// "Coming up" is measured from India's calendar day (R18-006). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { istToday } = await import("../src/lib/format.ts");

test("21:13 UTC on the 14th is already the 15th in India", (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-14T21:13:00Z") });
  assert.equal(istToday(), "2026-10-15");
});
