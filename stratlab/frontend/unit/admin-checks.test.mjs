// Admin's checks (owner, 4 Nov: "a whole check on admin pages — there are a lot of warnings"): a false or noisy warning fixed at the
// check, every Admin surface by one rule. Every value is fixed; no clock matters.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const ai = (name, result, extra = {}) => ({ name, label: name, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, ...extra });
const ov = (server = {}) => ({ server: { kite_ready: true, kite_token_day: null, feed_connected: true, live_sessions: 0, india_sessions: 0,
  auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, billing_hook: { mode: "live", last_at: "2026-10-28" },
  ai: [ai("groq", "working")], research: { finnhub: true }, recent_errors: [], server_started_at: "2026-11-04T22:00:00+05:30", ...server }, stats: {} });

test("Holidays known to 31 Dec are fine in November: the server's season-aware light is followed on every Admin surface", async () => {
  const { attention, services } = await import("../src/pages/admin/attention.ts");
  const nov = ov({ calendar: { days_left: 57, state: "ok", note: "Next year's list usually comes out in mid-December; the daily read adds it by itself. Nothing to do." } });
  const cal = services(nov).find((s) => s.key === "cal");
  assert.deepEqual([cal.state, cal.detail], ["ok", "Known for 57 more days · next year's list comes out in mid-December"]);
  assert.ok(!attention(nov, null, []).some((a) => /Exchange holidays/.test(a.text)));
  // from 20 Dec without next year's list: the server says warn, and Overview says so; under two weeks it is a Problem
  const late = (d) => ov({ calendar: { days_left: d, state: "warn", note: null } });
  assert.equal(services(late(10)).find((s) => s.key === "cal").state, "bad");
  assert.equal(services(late(20)).find((s) => s.key === "cal").state, "warn");
  assert.ok(attention(late(10), null, []).some((a) => a.text === "Exchange holidays are only known for 10 more days."));
  // an older server (no state): its days-left thresholds, as before
  assert.equal(services(ov({ calendar: { days_left: 57 } })).find((s) => s.key === "cal").state, "warn");
  assert.match(read("src/pages/admin/HolidaysPanel.tsx"), /const low = status\.state \? status\.state !== "ok" :/);
});
