// R41A: on a day the market is shut the pages name the last session, not a fault. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const { vixFreshness } = await import("../src/lib/vix.ts");

const FRIDAY_CLOSE = "2026-10-16T10:29:58Z";            // 15:59:58 IST on Friday 16 Oct

test("India VIX on a Saturday is the last session's, said as that and not as 'Not updated today'", () => {
  const f = vixFreshness({ quote: { as_of: FRIDAY_CLOSE }, value_day: null, intraday: [{ t: FRIDAY_CLOSE }, { t: FRIDAY_CLOSE }], today: "2026-10-17", session: "2026-10-16" });
  assert.equal(f.stale, false);
  assert.equal(f.lineStale, false);
  assert.match(f.lastSession, /^Last session \(Fri,? 16 Oct\)$/);
  assert.match(f.rangeLabel, /^Range on Fri,? 16 Oct$/);
  assert.match(f.lineTitle, /^Fri,? 16 Oct$/);
  assert.equal(f.stamp, "As of 16 Oct, 15:59 IST");
});

test("India VIX on a stored close from the last session is a last session too", () => {
  const f = vixFreshness({ quote: null, value_day: "2026-10-16", intraday: [], today: "2026-10-17", session: "2026-10-16" });
  assert.equal(f.stale, false);
  assert.match(f.lastSession, /^Last session \(Fri,? 16 Oct\)$/);
  assert.match(f.stamp, /^Close on Fri,? 16 Oct$/);
});

test("India VIX is 'not updated today' only when the market has had a session since the quote", () => {
  // Monday 19 Oct, 10:00 IST: the session is today's, the quote is still Friday's
  const f = vixFreshness({ quote: { as_of: FRIDAY_CLOSE }, value_day: null, intraday: [], today: "2026-10-19", session: "2026-10-19" });
  assert.equal(f.stale, true);
  assert.equal(f.lastSession, null);
  assert.match(f.rangeLabel, /^Range on Fri,? 16 Oct$/);
  // Monday 19 Oct, 06:30 IST: before the open the session is still Friday's, so Friday's quote is current
  const early = vixFreshness({ quote: { as_of: FRIDAY_CLOSE }, value_day: null, intraday: [], today: "2026-10-19", session: "2026-10-16" });
  assert.equal(early.stale, false);
  assert.match(early.lastSession, /Fri,? 16 Oct/);
});

test("a live reading on a trading day has no last-session note", () => {
  const f = vixFreshness({ quote: { as_of: "2026-10-16T05:00:00Z" }, value_day: null, intraday: [{ t: "2026-10-16T05:00:00Z" }], today: "2026-10-16", session: "2026-10-16" });
  assert.deepEqual([f.stale, f.lastSession, f.rangeLabel, f.lineTitle], [false, null, "Today's range", "Today"]);
});
