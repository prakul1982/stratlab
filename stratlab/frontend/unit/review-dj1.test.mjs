// 25 Oct 2026 deep audit of Admin (DJ-001 .. DJ-039), the page's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DJ-001: a 'Show test accounts' switch reads Overview and Users with them, and is left off by default", async () => {
  const { usersPath } = await import("../src/pages/admin/users.ts");
  assert.equal(usersPath("", "all"), "/admin/users?q=");
  assert.equal(usersPath("a", "pro", true), "/admin/users?q=a&plan=pro&test=1");
  const ctx = read("src/pages/admin/AdminContext.tsx");
  assert.match(ctx, /export function overviewPath\(fresh: boolean, test: boolean\)/);
  assert.match(ctx, /localStorage\.getItem\("admin-show-test"\) === "1"/);
  const users = read("src/pages/admin/UsersSection.tsx");
  assert.match(users, /<CheckField label=\{`Show test accounts/);
  assert.match(users, /<Badge dot=\{false\}>Test<\/Badge>/);
  assert.match(read("src/pages/admin/OverviewSection.tsx"), /test accounts left out/);
});

test("DJ-011, DJ-014: a given plan says 'ends today' or 'ended' by the India day, its note always under the badge", async () => {
  const { planNote, untilWords } = await import("../src/pages/admin/users.ts");
  const now = new Date("2026-10-24T20:00:00Z");                                   // 01:30 IST on 25 Oct
  assert.equal(untilWords("2026-10-24T18:00:00Z", now), "ended 24 Oct 2026");
  assert.equal(untilWords("2026-10-25T10:00:00Z", now), "ends today");
  assert.equal(untilWords("2026-11-06T10:00:00Z", now), "until 6 Nov 2026");
  assert.equal(planNote({ plan: "pro", paying: false, plan_until: "2026-10-24T18:00:00Z" }, now), "Given · ended 24 Oct 2026");
  assert.equal(planNote({ plan: "basic", paying: false, plan_until: null }, now), "Given · no end date");
  assert.match(read("src/pages/admin/UsersSection.tsx"), /<span className="k-stack adm-plan">/);
  assert.match(read("src/pages/admin/admin.css"), /\.adm-plan \{ align-items: flex-start/);
});

test("DJ-009, DJ-010, DJ-012: Last active sorts, the counts' month is in the headers, sign-ins without a profile are listed", async () => {
  const { monthShort } = await import("../src/pages/admin/users.ts");
  assert.equal(monthShort(new Date("2026-10-25T06:00:00Z")), "Oct");
  const src = read("src/pages/admin/UsersSection.tsx");
  assert.match(src, /\{ key: "active", header: "Last active", sortable: true/);
  assert.match(src, /header: `Experiments \(\$\{mon\}\)`/);
  assert.match(src, /header: `AI builds \(\$\{mon\}\)`/);
  assert.match(src, /api<AccountsView>\(`\/admin\/accounts/);
  assert.match(src, /Signed in, no profile/);
  assert.match(src, /Given plans ending/);
});

test("DJ-015, DJ-019: prices say Fixed with the day they were set, the info text matches pricing.py, and each shows its rupee worth", async () => {
  const { priceLabel, aboutRupees } = await import("../src/pages/admin/prices.ts");
  assert.equal(priceLabel("default", "2026-10-24"), "Fixed (set 24 Oct)");
  assert.equal(priceLabel("owner", "2026-10-24"), "Fixed by you");
  assert.equal(priceLabel("follows", null), "Follows the rupee price");
  assert.equal(aboutRupees(7, 127), "about ₹889");
  assert.equal(aboutRupees(8, null), "");
  const panel = read("src/pages/admin/PricesPanel.tsx");
  assert.doesNotMatch(panel, />Automatic</);
  assert.doesNotMatch(panel, /follow the rupee price at today's exchange rate/);
  assert.match(panel, /doesn't move with the exchange rate, and changing the rupee price doesn't change it/);
  assert.match(panel, /<b>Read today's rates<\/b> only updates the "about ₹…" notes/);
});

test("DJ-002, DJ-007: AI providers waiting on their quota are one line; a cut line ends at a word; feeds keep their own case", async () => {
  const { attention, oneLine } = await import("../src/pages/admin/attention.ts");
  const p = (label, result, extra = {}) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, state_text: "Free quota used up for now; it resets on its own.", ...extra });
  const ai = [p("Groq", "working"), p("Gemini", "working"), p("Cerebras", "quota"), p("Z.ai", "quota"), p("Hugging Face", "paused"),
    p("SambaNova", "failed", { state_text: "Failing: timed out." })];
  const ov = { server: { kite_ready: true, feed_connected: true, live_sessions: 0, auto_login_configured: true, auto_login: { ok: true, message: "ok" }, ai, billing_enabled: true }, stats: {} };
  const items = attention(ov, null, [{ id: "events", name: "Market events", schedule: "x", last_run: "2026-10-24T13:00:00Z", error: "Partial: 4 of 5 sources read. Not read: Index provider: down.", state: "warn" }]).map((a) => a.text);
  // LIVE1C-003: what resets on its own ("nothing to do") and a passing server fault are on the AI light, not in Needs your attention
  assert.ok(!items.some((t) => /paused for now|nothing to do/.test(t)), items.join("\n"));
  assert.ok(!items.some((t) => t.startsWith("AI, SambaNova")), items.join("\n"));
  const rejected = attention({ ...ov, server: { ...ov.server, ai: [...ai, p("Mistral", "failed", { state_text: "401: the key was rejected." })] } }, null, []).map((a) => a.text);
  assert.ok(rejected.includes("AI, Mistral: 401: the key was rejected."), rejected.join("\n"));
  assert.ok(!items.some((t) => t.startsWith("AI, Cerebras")));
  assert.ok(items.some((t) => t.includes("Market events (Partial: 4 of 5 sources read. Not read: Index provider: down.)")), items.join("\n"));
  const cut = oneLine("SambaNova is currently experiencing high demand and cannot serve the request right now please", 40);
  assert.equal(cut.text, "SambaNova is currently experiencing…");
});

test("DJ-003: on a weekend a logged-out broker is OK, with the next login's day and time", async () => {
  const { services } = await import("../src/pages/admin/attention.ts");
  const sv = { kite_ready: false, kite_invalid: "Zerodha has cancelled that login", feed_connected: false, live_sessions: 0, auto_login_configured: true,
    auto_login: { ok: true, message: "Logged in", at: "2026-10-24T02:30:00Z" }, auto_login_next: "2026-10-25T08:00+05:30", ai: [], billing_enabled: true,
    data_note: { closed: "weekend", back_at: "2026-10-25T08:00+05:30" } };
  const s = Object.fromEntries(services({ server: sv, stats: {} }).map((x) => [x.key, x]));
  assert.equal(s.kite.state, "ok");
  assert.equal(s.kite.detail, "Markets closed for the weekend; next login Sun 25 Oct, 08:00 IST.");
  assert.equal(s.auto.state, "ok");
  assert.match(s.auto.detail, /^OK: Markets closed for the weekend; next login Sun 25 Oct, 08:00 IST\.$/);
  const weekday = Object.fromEntries(services({ server: { ...sv, data_note: { closed: null, back_at: null } }, stats: {} }).map((x) => [x.key, x]));
  assert.equal(weekday.auto.state, "warn");                                        // a cancelled login on a trading day is still a Check
  assert.match(weekday.auto.detail, /Next automatic login: Sun 25 Oct, 08:00 IST\./);
});

test("DJ-034, DJ-033: alert emails show Brevo's sends against what is left today, and don't promise Telegram the server lacks", async () => {
  const { services, quotaLine, mailFix } = await import("../src/pages/admin/attention.ts");
  const q = { sent_today: 12, left_today: 288, plan: "free", limit_kind: "sendLimit", error: null, dashboard: "https://app.brevo.com/x" };
  assert.equal(quotaLine(q).text, "12 emails sent today, 288 left of today's limit (Brevo's free plan)");
  assert.equal(quotaLine({ ...q, sent_today: 290, left_today: 10 }).low, true);
  assert.equal(quotaLine({ ...q, sent_today: null, left_today: null }), null);
  const sv = { kite_ready: true, feed_connected: true, live_sessions: 0, auto_login_configured: true, auto_login: { ok: true, message: "ok" }, ai: [], billing_enabled: true,
    admin_alerts: { email_ready: true, via: "Brevo", to: ["owner@example.com"], quota: { ...q, sent_today: 295, left_today: 5 } } };
  const mail = services({ server: sv, stats: {} }).find((x) => x.key === "mail");
  assert.equal(mail.state, "warn");
  assert.match(mail.detail, /^Sent through Brevo · 295 emails sent today, 5 left of today's limit/);
  assert.match(mailFix(mail.fix, false), /plus your phone if set in Account \(Telegram isn't set up on the server\)\.$/);
  assert.equal(mailFix(mail.fix, true), mail.fix);
  assert.match(read("src/pages/admin/SystemSection.tsx"), /mailFix\(mail\.fix, chans\?\.telegram\)/);
});

test("DJ-026: the audit's mismatch count on Overview says when those rows were checked, and each row carries its date", async () => {
  const { attention } = await import("../src/pages/admin/attention.ts");
  const sv = { kite_ready: true, feed_connected: true, live_sessions: 0, auto_login_configured: true, auto_login: { ok: true, message: "ok" }, ai: [], billing_enabled: true,
    audit_mismatches: { IN: 49, US: 19 }, audit_checked: { IN: { oldest: "2026-10-05T04:00:00Z", newest: "2026-10-09T04:00:00Z" }, US: { oldest: "2026-10-07T04:00:00Z", newest: "2026-10-07T09:00:00Z" } } };
  const items = attention({ server: sv, stats: {} }, null, []).map((a) => a.text);
  assert.ok(items.includes("The whole-market audit has companies whose numbers disagree with their source: 49 in India (checked 5 Oct to 9 Oct), 19 in the US (checked 7 Oct)."), items.join("\n"));
  const panel = read("src/pages/admin/AuditPanel.tsx");
  assert.match(panel, /checked \{fmtDate\(r\.at, \{ year: false \}\)\}/);
  assert.match(panel, /\["symbol", "name", "checked", "level", "area", "detail", "first_found"\]/);
});

test("DJ-028, DJ-030: an old audit says how old, and the findings come 30 companies at a time", () => {
  const panel = read("src/pages/admin/AuditPanel.tsx");
  assert.match(panel, /const STALE_DAYS = 7;/);
  assert.match(panel, /These results are \$\{days\} days old/);
  assert.match(panel, /\{!s\.running && staleNote\(s\.finished_at\) && <Notice tone="warn">/);
  assert.match(panel, /const PAGE_ROWS = 30;/);
  assert.match(panel, /rows\.slice\(0, Math\.min\(SHOWN, upTo\)\)/);
});

test("DJ-031: a provider's badge reads its last result, as the summary counts it", async () => {
  const { providerWord } = await import("../src/pages/admin/aiBlocks.ts");
  assert.deepEqual(providerWord({ state: "ok", result: "failed", ranked_at: 1, discovered: 3 }), ["bad", "Failing"]);
  assert.deepEqual(providerWord({ state: "idle", result: "untested", ranked_at: 1, discovered: 0 }), [null, "Not tried · key may be wrong"]);
  assert.deepEqual(providerWord({ state: "idle", result: "untested", ranked_at: null, discovered: null }), [null, "Not tried yet"]);
  assert.deepEqual(providerWord({ state: "warn", result: "quota", ranked_at: 1, discovered: 3 }), ["warn", "Out of credit"]);
  assert.deepEqual(providerWord({ state: "ok", result: "working", ranked_at: 1, discovered: 3 }), ["ok", "Working"]);
  assert.deepEqual(providerWord({ state: "warn", ranked_at: 1, discovered: 3 }), ["warn", "Check"]);          // an older server
  assert.match(read("src/pages/admin/AIPanel.tsx"), /const \[light, word\] = providerWord\(p\);/);
});

test("DJ-036: each AI provider is one line until opened", () => {
  const panel = read("src/pages/admin/AIPanel.tsx");
  assert.match(panel, /<Disclosure summary=\{`Models, limits and controls/);
  assert.match(panel, /testId=\{`ai-details-\$\{p\.name\}`\}/);
});

test("DJ-032: the feature check says when its results come from an older build, and which end of the run list is newest", () => {
  const src = read("src/pages/admin/PlatformPanel.tsx");
  assert.match(src, /These results are from an older build \(\{r\.build\}\); this server now runs/);
  assert.match(src, /Last \{history\.length\} runs, oldest first:.*\(newest\)/);
  assert.match(src, /n >= 7 && ran\.slice\(0, n\)\.toLowerCase\(\) !== now\.slice\(0, n\)\.toLowerCase\(\)/);
});

test("DJ-033, DJ-037: the filings row shows the automatic check's result; the build words say something", () => {
  const src = read("src/pages/admin/SystemSection.tsx");
  assert.match(src, /c = x\.last\?\.checks\.find\(\(k\) => k\.name === "Exchange filings"\)/);
  assert.match(src, /In the check \$\{ago\(auto\.at\)\}: \$\{auto\.check\.detail\}/);
  assert.doesNotMatch(src, /"Known"/);
  assert.match(src, /"Same as the server"/);
});

test("DJ-035: server errors are grouped by kind and place, newest first, with a known upstream fault in plain words", async () => {
  const { groupErrors } = await import("../src/pages/admin/attention.ts");
  const e = (ref, at, error, where = "contextlib.py:158 in __exit__") => ({ ref, at, method: "GET", path: "/me", error, where });
  const g = groupErrors([e("a1", "2026-10-24T10:00:00Z", "RemoteProtocolError: Server disconnected"), e("a2", "2026-10-24T12:00:00Z", "RemoteProtocolError: Server disconnected"),
    e("b1", "2026-10-24T11:00:00Z", "KeyError: 'x'", "main.py:10 in me")]);
  assert.equal(g.length, 2);
  assert.equal(g[0].count, 2);
  assert.equal(g[0].ref, "a2");
  assert.match(g[0].plain, /^A connection to an outside service \(usually the database\) dropped/);
  assert.equal(g[1].plain, null);
});

test("DJ-004, DJ-005, DJ-006, DJ-008: Overview puts what needs you first, names the restart count, adds money and use, and folds the OK feeds", async () => {
  const { revenueText } = await import("../src/pages/admin/attention.ts");
  assert.equal(revenueText({ USD: 16, INR: 6990 }), "INR 6,990 · USD 16");
  const src = read("src/pages/admin/OverviewSection.tsx");
  assert.ok(src.indexOf('<Card label="Needs your attention">') < src.indexOf("<ViewAsCard />"));
  assert.match(src, /label: "Server errors \(since restart\)"/);
  assert.match(src, /label: "Revenue, last 30 days"/);
  assert.match(src, /label: "Active users, last 7 days"/);
  assert.match(src, /Bills StratLab can't read:/);
  assert.match(src, /<Disclosure summary=\{`Show the \$\{okFeeds\.length\} feeds that are OK`\}/);
});

test("DJ-016, DJ-017, DJ-018: Money reads Razorpay's lists and facts; the invoice form is one click away", async () => {
  const money = read("src/pages/admin/MoneySection.tsx");
  assert.match(money, /api<Activity>\("\/admin\/billing\/activity"\)/);
  assert.match(money, /Failed payments \(\{act\.failed\.length\}\)/);
  assert.match(money, /no webhook received yet/);
  const inv = read("src/pages/admin/InvoiceAdminPanel.tsx");
  assert.match(inv, /<Disclosure summary="Edit the invoice details" testId="invoice-edit">/);
  assert.match(money, /setAttribute\("open", ""\)/);                               // "Fill them in" opens it
});

test("DJ-020, DJ-025: storage shows a meter per real database, and the reclaim step in plain words with the SQL folded away", () => {
  const src = read("src/pages/admin/StoragePanel.tsx");
  assert.match(src, /meters\.map\(\(d\) => <DbLine key=\{d\.name\} d=\{d\} \/>\)/);
  assert.match(src, /Volume size on/);
  assert.match(src, /copies left from before users' data moved to Railway/);
  assert.match(src, /<Disclosure summary="Show the step, for Supabase's SQL Editor"/);
  assert.doesNotMatch(src, /run <code>vacuum full/);
});

test("DJ-013, DJ-023: the job buttons are quiet and the tables are cards on a phone; session cells break inside the card", () => {
  const data = read("src/pages/admin/DataSection.tsx");
  assert.match(data, /className="btn quiet sm" disabled=\{j\.running/);
  assert.match(data, /columns=\{cols\} stack phonePage=\{8\} \/>/);
  const users = read("src/pages/admin/UsersSection.tsx");
  assert.match(users, /<DataTable label="Paper trading sessions"[^\n]*stack \/>/);
  assert.match(users, /<span className="adm-break">\{s\.email\}<\/span>/);
});

test("DJ-029: rate sources show their unit and what uses them, not code paths", () => {
  const src = read("src/pages/admin/RulesPanel.tsx");
  assert.match(src, /`\$\{s\.shown\}\$\{s\.unit \?\? ""\}`/);
  assert.match(src, /Used for: \$\{s\.used\}\./);
  assert.doesNotMatch(src, /\(\{s\.where\}, \{ago/);
});

test("DJ-038: made-up email previews are marked as samples", () => {
  const src = read("src/pages/admin/EmailSection.tsx");
  assert.match(src, /<Badge tone="warn" dot=\{false\}>Sample<\/Badge>/);
  assert.match(src, /adm-mail-stage\$\{mail\.sample \? " sample" : ""\}/);
  assert.match(read("src/pages/admin/admin.css"), /content: "SAMPLE · made-up details"/);
});
