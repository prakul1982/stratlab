// Round 33: plans and breadth page copy. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

const { unlimitedLabel, FEATURES, AI_BUILDS_PER_DAY } = await import("../src/lib/plans.ts");
const { latestDue } = await import("../src/lib/format.ts");
const offer = await import("../src/lib/offer.ts");

test("R33-007: Pro's unlimited AI builds name the daily cap, from the card's constant", () => {
  assert.equal(unlimitedLabel("pro", "ai_builds_per_month"), `Unlimited (up to ${AI_BUILDS_PER_DAY} a day)`);
  assert.equal(unlimitedLabel("pro", "backtests_per_month"), "Unlimited");
  assert.ok(FEATURES.pro.some((f) => f.includes(`up to ${AI_BUILDS_PER_DAY} AI builds a day`)));
});

test("R33-001: a failed update is said plainly, not 'due about' after the time", () => {
  const p = { day: "2026-10-15", due: "5:55 PM ET", failed: true };
  assert.equal(latestDue("2026-10-14", p), "Latest: 14 Oct · the 15 Oct update didn't finish; it is tried again automatically");
  assert.match(latestDue("2026-10-14", { ...p, failed: false }), /due about 5:55 PM ET/);
});

test("R33-008: the Plans lede is true for a Free viewer too", () => {
  const i = offer.pricingIntro({ mode: "paid", payments: true }, {}, "app");
  assert.match(i.lede, /^Paid plans: cancel any time; the plan stays active until the paid period ends\.$/);
});

test("R33-003: a Free trial that ended says what happens to sessions", async () => {
  const { sessionsRunning, viewedFreeKeepsSessions } = await import("../src/lib/account.ts");
  const ended = { started: true, active: false, ends_at: "2026-10-14T18:30:00Z", available: false };
  const viewed = { plan: "free", view_as: "free", trial: ended, live_running: 1, live_limit: 1 };
  assert.ok(viewedFreeKeepsSessions(viewed));
  assert.match(sessionsRunning(viewed), /^1 of 1 \(kept running: you're viewing as Free/);
  assert.equal(sessionsRunning({ ...viewed, view_as: null }), "1 of 1");
  assert.equal(sessionsRunning({ ...viewed, trial: { ...ended, active: true } }), "1 of 1");
});
