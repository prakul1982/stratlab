// Lane social103 (owner, 28 Nov: "daily posting on X and LinkedIn fully automated; I have no time to post"): Admin → Social, and what the daily
// post puts in Needs your attention: LinkedIn's 60-day sign-in a week before it ends, a sign-in turned down, a post that failed both tries.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { attention, socialItems, LINKEDIN_WARN_DAYS } = await import("../src/pages/admin/attention.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const row = (key, over = {}) => ({ key, name: key === "x" ? "X" : "LinkedIn", configured: true, connected: true, enabled: true, expires_at: null,
  days_left: null, problem: null, failed: null, ...over });
const server = (social) => ({ kite_ready: true, kite_token_day: "2026-11-28", feed_connected: true, live_sessions: 0, auto_login: { at: null, ok: true, message: "ok" },
  auto_login_configured: true, billing_enabled: true, ai: [{ name: "g", label: "G", configured: true, in_use: true, model: "m", last_error: null, answering: true, result: "working" }],
  admin_alerts: { email_ready: true, to: [] }, invoice_seller: { complete: true, missing: [], gst: true }, social });

test("LinkedIn's sign-in: reconnect within N days from a week before it ends, never earlier", () => {
  assert.equal(LINKEDIN_WARN_DAYS, 7);
  assert.deepEqual(socialItems([row("linkedin", { days_left: 8, expires_at: "2026-12-06T04:00:00+00:00" })]), []);
  const [six] = socialItems([row("linkedin", { days_left: 6, expires_at: "2026-12-04T04:00:00+00:00" })]);
  assert.match(six.text, /^Reconnect LinkedIn within 6 days: its sign-in ends on 4 Dec 2026/);
  assert.equal(six.to, "/admin/social");
  assert.equal(six.label, "Social");
  assert.match(socialItems([row("linkedin", { days_left: 0 })])[0].text, /within a day/);
  // said even with posting off (the sign-in ends all the same), never for one not connected
  assert.equal(socialItems([row("linkedin", { days_left: 3, enabled: false })]).length, 1);
  assert.deepEqual(socialItems([row("linkedin", { days_left: 3, connected: false })]), []);
  const ended = socialItems([row("linkedin", { days_left: -1, expires_at: "2026-11-27T04:00:00+00:00" })])[0];
  assert.match(ended.text, /^LinkedIn's sign-in has ended \(27 Nov 2026\)/);
  assert.equal(ended.bad, true);
});

test("a post that failed both tries, or may not have gone out, is the owner's; a network switched off asks for nothing", () => {
  const failed = socialItems([row("x", { failed: { at: "2026-11-28T04:30:00Z", status: "failed", error: "X answered 403: You are not permitted to perform this action.", day: "2026-11-28" } })]);
  assert.equal(failed.length, 1);
  assert.match(failed[0].text, /^X daily post failed twice: X answered 403/);
  assert.equal(failed[0].bad, true);
  const unknown = socialItems([row("x", { failed: { at: null, status: "unknown", error: "X didn't answer in time.", day: "2026-11-28" } })]);
  assert.match(unknown[0].text, /^X daily post may not have gone out/);
  assert.deepEqual(socialItems([row("x", { enabled: false, failed: { at: null, status: "failed", error: "e", day: "d" } })]), []);
  const turned = socialItems([row("x", { connected: false, problem: "X turned the stored sign-in down: press Connect X again." })]);
  assert.match(turned[0].text, /^X daily post: X turned the stored sign-in down/);
  assert.deepEqual(socialItems(undefined), []);
  assert.deepEqual(socialItems([row("x"), row("linkedin", { days_left: 40 })]), []);
});

test("Overview's Needs your attention carries the social items; an older server without them changes nothing", () => {
  const items = attention({ server: server([row("linkedin", { days_left: 2 })]), stats: {} }, null, []);
  assert.ok(items.some((a) => /^Reconnect LinkedIn within 2 days/.test(a.text)));
  const none = attention({ server: server(undefined), stats: {} }, null, []);
  assert.ok(!none.some((a) => /LinkedIn|X daily/.test(a.text)));
});

test("Admin → Social is a section of its own, and the page never handles a token", () => {
  const ctx = read("src/pages/admin/AdminContext.tsx");
  assert.match(ctx, /\{ path: "social", label: "Social"/);
  const page = read("src/pages/admin/SocialSection.tsx");
  assert.doesNotMatch(page, /access_token|refresh_token|localStorage/);
  // the sign-in starts on the server and the browser only follows the address it is given
  assert.match(page, /\/admin\/social\/\$\{n\.key\}\/connect/);
  assert.match(page, /window\.location\.assign\(url\)/);
  assert.match(read("src/pages/AdminPage.tsx"), /<Route path="social" element=\{<SocialSection \/>\} \/>/);
});
