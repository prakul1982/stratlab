// Breadth thrust days: a list spanning years carries every year. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const { thrustDays } = await import("../src/lib/breadth.ts");

test("thrust days spanning years carry every year; days all in this year stay short (R35)", () => {
  const y = new Date().getFullYear();
  const mixed = thrustDays([`${y - 1}-04-16`, `${y}-04-08`]);
  assert.match(mixed, new RegExp(`16 Apr ${y - 1}`));
  assert.match(mixed, new RegExp(`8 Apr ${y}`));
  assert.equal(thrustDays([`${y}-04-08`, `${y}-05-02`]), "8 Apr, 2 May");
});
