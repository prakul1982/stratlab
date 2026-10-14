// Round 18 review of the core strategy product: the app's side. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

const R = await import("../src/lib/rules.ts");

test("R18-002: the plain-words converter reads a 52-week low as the lowest low of 252 candles, never as a number", () => {
  const p = R.parseStrategyText("Buy when price touches its 52-week low and volume is above average volume 20");
  const rule = p.entry.find((c) => c.r.t === "dc_lower");
  assert.ok(rule, JSON.stringify(p.entry));
  assert.deepEqual(rule, { l: { t: "low" }, op: "lt", r: { t: "dc_lower", p: 252 } });
  assert.ok(!p.entry.some((c) => c.r.t === "num" && c.r.v === 52));
  const below = R.parseStrategyText("Buy when the price is below the 52 week low. Sell when it crosses above the 52-week high");
  assert.deepEqual(below.entry[0], { l: { t: "price" }, op: "lt", r: { t: "dc_lower", p: 252 } });
  assert.deepEqual(below.exit[0].r, { t: "dc_upper", p: 252 });
});

test("R18-002: 'reaches' and 'hit' still read as before when no 52-week level follows", () => {
  const p = R.parseStrategyText("Buy when RSI reaches above 30. Sell when RSI is above 55");
  assert.equal(p.entry.length, 1);
  assert.equal(p.entry[0].op, "gt");
});

test("R18-002: a price against 0 is left out as a rule that can't mean anything, and the rules editor says so", () => {
  const dead = { l: { t: "price" }, op: "lt", r: { t: "num", v: 0 } };
  assert.deepEqual(R.meaningful([dead]).dropped, ["Price is below 0"]);
  const src = read("src/components/Rules.tsx");
  assert.match(src, /meaningful\(\[\.\.\.s\.entry/);
  assert.match(src, /can't mean anything as a rule/);
});
