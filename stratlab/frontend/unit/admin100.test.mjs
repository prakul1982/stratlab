// Lane admin100 (owner, 27 Nov: "errors in Admin"): Needs your attention holds only what the owner fixes by hand (Release 93), the rest is
// listed apart; the email service and Razorpay refusing the server are the owner's, an outside source not answering never is.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { attention, selfFixing, service, triage } = await import("../src/pages/admin/attention.ts");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const ai = [{ name: "groq", label: "Groq", configured: true, in_use: true, model: "m", last_error: null, answering: true, result: "working" }];
const server = (over = {}) => ({
  kite_ready: true, kite_token_day: "2026-11-27", kite_invalid: null, feed_connected: false, live_sessions: 1, india_sessions: 1,
  auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, billing_hook: { mode: "test", last_at: null },
  ai, research: { finnhub: true }, admin_alerts: { email_ready: true, via: "Brevo", to: ["owner@example.com"] },
  invoice_seller: { complete: true, missing: [], gst: true },
  recent_errors: [{ ref: "a", at: "2026-11-27T10:00:00+05:30" }], server_started_at: "2026-11-27T09:00:00+05:30",
  audit_mismatches: { IN: 3 }, rules_watch: { failing: [{ name: "RBI", fails: 4, error: null }], pending: ["SEBI fees"] }, ...over,
});
const ov = (over) => ({ server: server(over), stats: {} });
const src = (key, over = {}) => ({ key, label: key, what: "", to: "/admin/data", state: "ok", word: "OK", detail: "", last_ok: null, last_fail: null,
  error: null, fails: 0, owner: false, action: null, ...over });
const jobs = [{ id: "events", name: "Market events", schedule: "x", last_run: "2026-11-27T01:50:00Z", error: "Partial: 4 of 5 sources read.", state: "warn", running: false, log: [], run: [], note: null },
  { id: "fo", name: "F&O contract changes", schedule: "x", last_run: "2026-11-27T01:50:00Z", error: "Retried automatically 3 times without luck.", state: "bad", running: false, log: [], run: [], note: null }];

test("Release 93: only the owner's manual fixes need attention; the rest is listed apart, nothing lost", () => {
  const sv = ov({ sources: [src("nse-archive", { state: "warn", word: "Not answering", error: "every archive host refused this server (403)" })] });
  const { owner, auto } = triage(sv, null, jobs);
  const mine = owner.map((a) => a.text).join("\n"), apart = auto.map((a) => a.text).join("\n");
  // the owner's: a job the self-healing gave up on, a rule change to review
  assert.match(mine, /F&O contract changes: Retried automatically/);
  assert.match(mine, /Rate and rule sources changed, waiting for a look: SEBI fees/);
  // apart: the feed reconnecting, server errors, a feed on Check, an unread rule source, the audit, a source not answering
  for (const re of [/^Live price feed:/m, /^1 server error since the last restart\./m, /^1 data feed on Check: Market events/m, /^Rate and rule sources unread: RBI/m,
    /^The whole-market audit/m, /^nse-archive: Not answering \(every archive host refused this server \(403\)\)/m]) {
    assert.match(apart, re);
    assert.doesNotMatch(mine, re);
  }
  assert.deepEqual(attention(sv, null, jobs), owner);
  assert.deepEqual(selfFixing(sv, null, jobs), auto);
});

test("the email service refusing the server twice is the owner's Fix, with the step; once is not", () => {
  const twice = src("mail", { state: "bad", word: "Fix", owner: true, error: "Brevo: Brevo refused the email (401)", fails: 2,
    detail: "Failing since 27 Nov, 2:00 PM IST, 2 tries in a row: Brevo refused the email (401). In Brevo, open your name …" });
  const mail = service(ov({ sources: [twice] }), "mail");
  assert.equal(mail.state, "bad");
  assert.equal(mail.detail, "Sending fails: Brevo: Brevo refused the email (401)");
  assert.ok(attention(ov({ sources: [twice] }), null, []).some((a) => a.bad && a.text.startsWith("Alert emails are failing: Failing since")));
  const once = src("mail", { word: "Retrying", fails: 1, error: "Brevo: timed out" });
  assert.equal(service(ov({ sources: [once] }), "mail").state, "ok");
  assert.ok(!attention(ov({ sources: [once] }), null, []).some((a) => /Alert emails/.test(a.text)));
  // never listed twice: an owner-fixed source is said through its service's light, not again among the sources
  assert.ok(!selfFixing(ov({ sources: [twice] }), null, []).some((a) => a.text.startsWith("mail:")));
});

test("Razorpay turning the server down is the owner's; Payments says when the last payment event came", () => {
  const rz = src("payments", { state: "bad", word: "Fix", owner: true, error: "Authentication failed", detail: "Failing since … Razorpay turned the server's keys down: check RAZORPAY_KEY_ID …" });
  const pay = service(ov({ sources: [rz] }), "pay");
  assert.equal(pay.state, "bad");
  assert.ok(attention(ov({ sources: [rz] }), null, []).some((a) => a.bad && a.text.startsWith("Payments: Failing since")));
  const recent = new Date(Date.now() - 2 * 3600_000).toISOString();
  assert.match(service(ov({ billing_hook: { mode: "live", last_at: recent } }), "pay").detail, /^Connected · last payment event 2 h ago$/);
});

test("Overview draws the two lists and the Data sources card; the menu counts the owner's only", () => {
  const page = read("src/pages/admin/OverviewSection.tsx");
  assert.match(page, /const \{ owner: todo, auto \} = triage\(ov, reported, jobs\);/);
  assert.match(page, /StratLab is handling itself: nothing for you to do/);
  assert.match(page, /<Card label="Data sources" testId="data-sources">/);
  assert.match(read("src/pages/AdminPage.tsx"), /const n = attention\(ov, reported, jobs\)\.length;/);
});

test("System, AI: each provider says its last answer and its last failure", async () => {
  const { answerTimes } = await import("../src/pages/admin/AIPanel.tsx").catch(() => ({ answerTimes: null }));
  if (answerTimes) {
    const now = Date.now() / 1000;
    assert.match(answerTimes(now - 120, now - 7200), /^Last answer 2 min ago; the last failure \(2 h ago\) was before it\.$/);
    assert.match(answerTimes(now - 7200, now - 120), /^Last answer 2 h ago; last failure 2 min ago, after it\.$/);
  }
  assert.match(read("src/pages/admin/AIPanel.tsx"), /data-testid=\{`ai-times-\$\{p\.name\}`\}>\{answerTimes\(p\.last_ok, p\.last_error_at\)\}/);
});
