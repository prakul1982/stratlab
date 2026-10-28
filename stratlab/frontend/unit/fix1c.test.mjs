// FIX-1C: the live-site review LIVE-1C (Admin, emails, plan views, the owner's real data), the page's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const base = { kite_ready: true, feed_connected: true, live_sessions: 0, auto_login_configured: true, auto_login: { ok: true, message: "Logged in to Kite." }, ai: [], billing_enabled: true };

test("LIVE1C-003: Needs your attention holds what must be done; what resets by itself is on the AI light", async () => {
  const { attention, passingFault, services } = await import("../src/pages/admin/attention.ts");
  assert.ok(passingFault("Last try failed: server error 503") && passingFault("Failing: timed out.") && passingFault("rate limit, try again"));
  assert.ok(!passingFault("401: the key was rejected.") && !passingFault("403: AI Gateway requires a valid credit card on file"));
  const p = (label, result, state_text) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, state_text });
  const ov = { server: { ...base, ai: [p("Groq", "working", ""), p("Gemini", "failed", "Last try failed: server error 503"), p("Cerebras", "quota", "Free quota used up"), p("Mistral", "failed", "401: key rejected")] }, stats: {} };
  const items = attention(ov, null, []).map((a) => a.text);
  assert.deepEqual(items, ["AI, Mistral: 401: key rejected"]);
  assert.match(services(ov).find((s) => s.key === "ai").detail, /2 failing|1 out of credit/);          // the rest is said on the light
});

test("LIVE1C-004, LIVE1C-024: the link sits under the sentence, never in a column of its own", () => {
  assert.match(read("src/pages/admin/OverviewSection.tsx"), /<span className="adm-todo-body"><span title=\{x\.full\}>\{x\.text\}<\/span><Link className="link" to=\{x\.to\}>Open \{x\.label\} →<\/Link><\/span>/);
  const css = read("src/pages/admin/admin.css");
  assert.match(css, /\.adm-todo-body \{ display: flex; flex-direction: column; align-items: flex-start/);
  assert.match(css, /\.adm-todo-body > \.link \{ white-space: nowrap; \}/);
});

test("LIVE1C-005: this month's counts sit in Money, use and limits; a row of feed tiles fills its width", () => {
  const src = read("src/pages/admin/OverviewSection.tsx");
  assert.doesNotMatch(src, /<Card label="This month">/);
  assert.match(src, /label="Experiments this month"/);
  assert.match(src, /label="AI builds this month"/);
  assert.match(src, /data-testid="posthog-dashboard"/);
  assert.match(read("src/styles.css"), /\.k-health \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(190px, 1fr\)\)/);
});

test("LIVE1C-007: subscriptions say how many started, were paid and failed; unpaid checkouts are folded", async () => {
  const { subsSummary } = await import("../src/pages/admin/subs.ts");
  const open = Array.from({ length: 25 }, () => ({ status: "created", paid_count: 0 }));
  assert.equal(subsSummary({ subscriptions: open, failed: [{}] }), "25 started, 0 paid, 1 failed payment; 25 checkouts were opened and never paid.");
  assert.equal(subsSummary({ subscriptions: [{ status: "active", paid_count: 2 }], failed: [] }), "1 started, 1 paid, 0 failed payments.");
  const src = read("src/pages/admin/MoneySection.tsx");
  assert.match(src, /header: "User", rowHeader: true/);
  assert.match(src, /header: "Amount"/);
  assert.match(src, /testId="subs-unpaid"/);
});

test("LIVE1C-008: live keys that never got a payment event are a Check on Services and in the list", async () => {
  const { services, attention } = await import("../src/pages/admin/attention.ts");
  const ov = (hook) => ({ server: { ...base, billing_hook: hook }, stats: {} });
  const pay = (o) => services(o).find((s) => s.key === "pay");
  assert.equal(pay(ov({ mode: "live", last_at: null })).state, "warn");
  assert.match(pay(ov({ mode: "live", last_at: null })).detail, /never sent a payment event: send a test event before the first payment/);
  assert.equal(pay(ov({ mode: "live", last_at: "2026-10-28T10:00:00Z" })).state, "ok");
  assert.equal(pay(ov({ mode: "test", last_at: null })).state, "ok");
  assert.ok(attention(ov({ mode: "live", last_at: null }), null, []).some((a) => a.text.startsWith("Payments: Connected, but Razorpay has never sent")));
});

test("LIVE1C-009: the prices table marks only what differs, and one picker opens a currency's Razorpay plans", () => {
  const src = read("src/pages/admin/PricesPanel.tsx");
  assert.doesNotMatch(src, /Razorpay plans<\/button>/);
  assert.match(src, /id="price-plan-currency"/);
  assert.match(src, /list\.some\(\(\{ r \}\) => odd\(r\)\)/);
});

test("LIVE1C-011, LIVE1C-012: the sessions follow the test switch; empty invite tables are one line", () => {
  const src = read("src/pages/admin/UsersSection.tsx");
  assert.match(src, /\/admin\/sessions\$\{showTest \? "\?test=1" : ""\}/);
  assert.match(src, /data-testid="rewards-none"/);
  assert.match(src, /className="btn outline sm">Start now<\/button>/);          // the launch offer is not the loudest button
});

test("LIVE1C-014, LIVE1C-015: a job's next run is a time with the schedule behind an (i); a card has no stray label", () => {
  const src = read("src/pages/admin/DataSection.tsx");
  assert.match(src, /Next run: \{j\.next\}/);
  assert.match(src, /<Info label=\{`Schedule of \$\{j\.name\}`\}>\{j\.schedule\}<\/Info>/);
  assert.match(src, /stack phonePage=\{8\}/);
  assert.match(read("src/styles.css"), /td\.k-act\[data-label\]::before \{ display: none; \}/);
});

test("LIVE1C-016: the automatic login line puts its full stop after the time and says what started it", async () => {
  const { services } = await import("../src/pages/admin/attention.ts");
  const at = new Date(Date.now() - 14 * 3600e3).toISOString();
  const sv = { ...base, kite_ready: true, auto_login: { ok: true, message: "Logged in to Kite.", at, how: "started from Admin" }, auto_login_next: "2099-10-29T08:00+05:30" };
  const d = services({ server: sv, stats: {} }).find((s) => s.key === "auto").detail;
  assert.match(d, /^Logged in to Kite 14 h ago \(.*IST, started from Admin\)\. Next automatic login: /);
  assert.doesNotMatch(d, /Kite\. \(/);
});

test("LIVE1C-017: each list of sizes says whose database it is, and the Railway total is split", () => {
  const src = read("src/pages/admin/StoragePanel.tsx");
  assert.match(src, /Biggest tables: users' data \(Railway\)/);
  assert.match(src, /Biggest tables: market data \(Railway\)/);
  assert.match(src, /data-testid="storage-split"/);
  assert.doesNotMatch(src, /Connected\{s\.market\.total != null/);
});

test("LIVE1C-018: the holiday paste box is tall enough for its placeholder", () => {
  assert.match(read("src/pages/admin/admin.css"), /\.adm-main textarea\.k-input \{ height: auto; min-height: 112px/);
});

test("LIVE1C-020: the audits' run and manage buttons are behind one fold each", () => {
  const src = read("src/pages/admin/AuditPanel.tsx");
  assert.match(src, /testId="audit-run"/);
  assert.match(src, /<Disclosure summary="Manage this check" testId="market-manage">/);
  assert.doesNotMatch(src, /FieldGroup label="Documents"/);
});

test("LIVE1C-022, LIVE1C-024: a server error is two lines with its program text behind Details", () => {
  const src = read("src/pages/admin/SystemSection.tsx");
  assert.match(src, /An unexpected error in the server\./);
  assert.match(src, /<Disclosure summary="Details" className="adm-err-details">/);
  assert.doesNotMatch(src, /header: "Where"/);
  assert.doesNotMatch(read("src/pages/admin/attention.ts"), /\(\$\{quota\.text\}\)/);          // no brackets inside brackets
});

test("LIVE1C-023: on a phone the long section names lose their tail visually and keep it for screen readers", () => {
  assert.match(read("src/pages/AdminPage.tsx"), /<span className="adm-tail">/);
  assert.match(read("src/pages/admin/admin.css"), /\.adm-tail \{ position: absolute; width: 1px/);
});

test("LIVE1C-038, LIVE1C-039: the email list says what StratLab does not send; the sample mark sits above the email", () => {
  assert.match(read("src/pages/admin/EmailSection.tsx"), /data-testid="not-sent-here"/);
  const css = read("src/pages/admin/admin.css");
  assert.match(css, /\.adm-mail-stage\.sample::before \{ content: "SAMPLE · made-up details"/);
  assert.doesNotMatch(css, /adm-mail-stage\.sample::after/);
});
