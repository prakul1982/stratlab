// Live visitor review, round 16. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { importWithRetry } = await import("../src/lib/lazyRetry.ts");

test("R16-001: a failed or empty import is asked for again before giving up", async () => {
  let n = 0;
  const m = await importWithRetry(async () => { n++; if (n === 1) throw new Error("Failed to fetch dynamically imported module"); if (n === 2) return undefined; return { ok: 1 }; }, [1, 1, 1]);
  assert.deepEqual(m, { ok: 1 });
  assert.equal(n, 3);
  let calls = 0;
  await assert.rejects(importWithRetry(async () => { calls++; throw new Error("x"); }, [1, 1, 1]));
  assert.equal(calls, 4, "one try and three more");
});

const { signedOutTitle, titleFor } = await import("../src/lib/title.ts");
const { lostMoney, LOST_CHECKS } = await import("../src/lib/tradeUi.ts");

test("R16-009: /plans and /faq tabs are titled by name, signed in or not", () => {
  assert.equal(signedOutTitle("/plans"), "Plans · StratLab");
  assert.equal(titleFor("/plans"), "Plans · StratLab");
  assert.equal(signedOutTitle("/faq"), "Questions · StratLab");
});

test("R16-006: a strategy that lost money has no pass count headlined", () => {
  assert.ok(lostMoney("no_edge", -3.2));
  assert.ok(!lostMoney("no_edge", 4));
  assert.ok(!lostMoney("edge", -3));
  assert.match(LOST_CHECKS, /lost money after costs/);
});
