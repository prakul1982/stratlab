// Admin's one reading of the server's status (Overview, Data and jobs and System say the same thing), the Users table's
// words and typed confirmation, Account's sign-in method and hand-given plans, and the invite page's words.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { attention, lights, paidUsers, service, services } = await import("../src/pages/admin/attention.ts");

test("Overview counts paying users apart from plans the owner gave", () => {
  const st = { users: 305, plans: { free: 102, basic: 101, pro: 102 }, new_7d: 4, experiments_month: 0, ai_month: 0 };
  assert.deepEqual(paidUsers({ ...st, paying: { basic: 0, pro: 0 }, given: { basic: 101, pro: 102 } }),
    { label: "Paying users", value: 0, note: "203 on a plan you gave, not paying" });
  assert.deepEqual(paidUsers({ ...st, paying: { basic: 3, pro: 1 }, given: { basic: 98, pro: 101 } }),
    { label: "Paying users", value: 4, note: "3 Basic · 1 Pro · 199 on a plan you gave, not paying" });
  assert.equal(paidUsers({ ...st, plans: { free: 1, basic: 0, pro: 0 }, paying: { basic: 0, pro: 0 }, given: { basic: 0, pro: 0 } }).note, "No paid plans");
  assert.equal(paidUsers(st).label, "Paid users");                // an older server: the plain count
});
const { confirmMatches, confirmWord, planNote, usersPath } = await import("../src/pages/admin/users.ts");
const { monthlyUse, planRow, planRun, signedInWith } = await import("../src/lib/account.ts");

test("Account: a monthly limit early access lifts says so, with the plan's own limit", () => {
  assert.equal(monthlyUse(3, 10), "3 of 10");
  assert.equal(monthlyUse(0, null), "0 (unlimited)");
  assert.equal(monthlyUse(0, null, 2, "early access", "Free"), "0 (unlimited during early access; Free has 2 a month)");
  assert.equal(monthlyUse(1, null, 1, "the launch offer", "Free"), "1 (unlimited during the launch offer; Free has 1 a month)");
  assert.equal(monthlyUse(0, null, null, "early access", "Pro"), "0 (unlimited)");          // Pro has no limit anyway
  assert.equal(monthlyUse(0, null, 2, null, "Free"), "0 (unlimited)");
});
const { FRIEND_GETS, inviteRows, youGet } = await import("../src/lib/invite.ts");

const server = (over = {}) => ({
  kite_ready: true, kite_token_day: "2026-10-07", kite_invalid: null, feed_connected: false, live_sessions: 0, india_sessions: 0,
  auto_login: { at: null, ok: null, message: "" }, auto_login_configured: false, billing_enabled: false,
  ai: [], research: { finnhub: true }, admin_alerts: { email_ready: false, via: null, to: ["owner@example.com"] }, ...over,
});
const ov = (over) => ({ server: server(over), stats: { users: 1, plans: { free: 1, basic: 0, pro: 0 }, new_7d: 0, experiments_month: 0, ai_month: 0 } });

test("Overview's lights and the rows on Data and jobs and System come from one reading", () => {
  for (const o of [ov(), ov({ india_sessions: 1, live_sessions: 1 }), ov({ feed_connected: true, india_sessions: 2, live_sessions: 3 }),
    ov({ kite_ready: false }), ov({ admin_alerts: { email_ready: true, via: "Resend", to: ["a@b.c"] } })]) {
    const tiles = lights(o, []).services;
    for (const key of ["kite", "feed", "auto", "mail", "co"]) {
      const row = service(o, key), tile = tiles.find((t) => t.key === key);
      assert.ok(row && tile, key);
      assert.equal(row.state, tile.state, `${key}: the same light`);
      assert.equal(row.detail, tile.detail, `${key}: the same words`);
    }
  }
});

test("the live price feed: idle without India sessions, even with other markets' sessions running", () => {
  const idle = service(ov({ live_sessions: 2, india_sessions: 0 }), "feed");
  assert.equal(idle.state, "ok");
  assert.match(idle.detail, /^Idle: no India paper sessions running$/);
  const down = service(ov({ live_sessions: 2, india_sessions: 1 }), "feed");
  assert.equal(down.state, "warn");
  assert.equal(down.detail, "Not connected, with 1 India paper session running");
  // a server that sends only the total still reads the same way
  const old = ov({ live_sessions: 1 }); delete old.server.india_sessions;
  assert.equal(service(old, "feed").state, "warn");
  // Overview's attention list names it, in the same words
  const todo = attention(ov({ live_sessions: 1, india_sessions: 1 }), null, []);
  assert.ok(todo.some((t) => t.text === "Live price feed: Not connected, with 1 India paper session running."));
});

test("alert email: one wording everywhere, naming the service in use or every way to set one up", () => {
  const off = ov();
  const mail = service(off, "mail");
  assert.equal(mail.state, "bad");
  assert.match(mail.fix, /RESEND_API_KEY/);
  assert.match(mail.fix, /BREVO_API_KEY/);
  assert.match(mail.fix, /SMTP_HOST, SMTP_USER and SMTP_PASSWORD/);
  const todo = attention(off, null, []).find((t) => t.label === "System" && /email/i.test(t.text));
  assert.match(todo.text, /no email service \(Resend, Brevo or SMTP\)/);
  assert.doesNotMatch(todo.text, /SMTP\) settings are missing/);
  const on = service(ov({ admin_alerts: { email_ready: true, via: "Resend", to: ["owner@example.com"] } }), "mail");
  assert.equal(on.detail, "Sent through Resend");
  assert.match(on.fix, /^Emailed to owner@example\.com through Resend/);
  assert.equal(services(ov({ admin_alerts: undefined })).some((s) => s.key === "mail"), false);
});

test("a job's partial run is Check on Overview, never in Needs your attention; a failed one is", () => {
  const jobs = [
    { id: "events", name: "Market events", schedule: "", last_run: "2026-10-07T07:20:00Z", error: "Partial: 4 of 5 sources read. Not read: Central bank (MPC): Couldn't reach www.rbi.org.in.", state: "warn", running: false, log: [], run: [], note: null },
    { id: "fo", name: "F&O contract changes", schedule: "", last_run: null, error: "contract file: no answer", state: "bad", running: false, log: [], run: [], note: null },
  ];
  const { feeds } = lights(ov(), jobs);
  assert.deepEqual(feeds.map((f) => f.state), ["warn", "bad"]);
  const todo = attention(ov(), null, jobs).map((t) => t.text);
  assert.ok(todo.includes("F&O contract changes: contract file: no answer"));
  assert.ok(!todo.some((t) => t.startsWith("Market events")));
});

test("Users: a plan's words, the plan filter in the address, and the typed confirmation", () => {
  assert.equal(planNote({ plan: "free", plan_until: null, paying: false }), "");
  assert.equal(planNote({ plan: "pro", plan_until: null, paying: false }), "Given · no end date");
  assert.equal(planNote({ plan: "basic", plan_until: "2026-11-06T00:00:00Z", paying: false }), "Given · until 6 Nov 2026");
  assert.equal(planNote({ plan: "basic", plan_until: "2026-11-05T00:00:00Z", paying: true }), "Razorpay · renews 5 Nov 2026");
  assert.equal(usersPath("", "all"), "/admin/users?q=");
  assert.equal(usersPath("load 1", "pro"), "/admin/users?q=load%201&plan=pro");
  assert.equal(confirmWord({ id: "u-1", email: "a@b.com" }), "a@b.com");
  assert.equal(confirmWord({ id: "u-1", email: null }), "u-1");
  assert.equal(confirmMatches(" A@B.com ", "a@b.com"), true);
  assert.equal(confirmMatches("a@b.co", "a@b.com"), false);
  assert.equal(confirmMatches("", ""), false);
});

test("Account: how you signed in never shows a dash", () => {
  assert.equal(signedInWith("google", null), "Google");
  assert.equal(signedInWith(undefined, "google"), "Google");
  assert.equal(signedInWith("", "email"), "Email link");
  assert.equal(signedInWith(null, "twitter"), "Twitter");
  assert.equal(signedInWith(undefined, null), null);
});

test("Account: a plan the owner gave has no renewal and nothing to cancel", () => {
  const me = (billing, paid = "pro") => ({ plan: paid, paid_plan: paid, billing: { subscribed_plan: paid, status: "active", renews_or_ends: null, cancel_at_period_end: false, ...billing } });
  assert.equal(planRun(me({ given_by_owner: true })), "given");
  assert.deepEqual(planRow(me({ given_by_owner: true })), ["Given by the owner", "No end date"]);
  assert.deepEqual(planRow(me({ given_by_owner: true, renews_or_ends: "2026-12-01T00:00:00Z" })), ["Given by the owner", "Until 1 Dec 2026"]);
  assert.equal(planRun(me({ renews_or_ends: "2026-11-05T00:00:00Z" })), "renews");
  assert.deepEqual(planRow(me({ renews_or_ends: "2026-11-05T00:00:00Z" })), ["Renews on", "5 Nov 2026"]);
  assert.deepEqual(planRow(me({ renews_or_ends: "2026-11-05T00:00:00Z", cancel_at_period_end: true })), ["Ends on", "5 Nov 2026"]);
  assert.equal(planRow(me({}, "free")), null);
  // the launch offer makes everyone Pro, but the plan they have is what counts
  assert.equal(planRun({ plan: "pro", paid_plan: "free", billing: { given_by_owner: false } }), "free");
});

test("Invite: plain words, and a paying user is never offered a month of Basic now", () => {
  const v = { code: "x", link: "", joined: 6, months: 3, use_months: 2, use_cap: 2, paid_months: 1, paid_cap: 2, extras: 0, extra_days: 8, waiting_to_subscribe: 1, banked_days: 60 };
  assert.match(FRIEND_GETS, /gets a month of Basic free/);
  const free = youGet(v, "free");
  assert.match(free, /^You get a month of Basic free for each of your first 2 friends who do this in a year/);
  const pro = youGet(v, "pro");
  assert.doesNotMatch(pro, /You get a month of Basic/);
  assert.match(pro, /You're on Pro, so it's kept for you and starts only if your Pro plan stops/);
  const rows = Object.fromEntries(inviteRows(v, "pro"));
  assert.equal(rows["This year: friends who used StratLab"], "2 of 2 months");
  assert.equal(rows["This year: friends who subscribed"], "1 of 2 months");
  assert.equal(rows["Waiting to subscribe"], "1 friend");
  assert.equal(rows["Kept for when your plan stops"], "60 days of Basic");
  for (const [k, val] of inviteRows(v, "free")) assert.doesNotMatch(`${k} ${val}`, /Use:|Extra:|weeks/);
  assert.equal(Object.fromEntries(inviteRows({ ...v, free_basic_until: "2026-11-01T00:00:00Z" }, "free"))["Free Basic"], "Until 1 Nov 2026");
});
