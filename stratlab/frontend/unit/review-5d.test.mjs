// Review 5d: the plan switch confirm, a currency with its own Razorpay plan, Account's real plan and View as, Admin's
// paying users, prices typed wrong, invoice details, the retry buttons, and the smaller wording items.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const { paymentWindowLine, switchEndsNote, viewingPlansNote } = await import("../src/lib/offer.ts");
const { planLabel, planRun, planRow } = await import("../src/lib/account.ts");
const { planNote } = await import("../src/pages/admin/users.ts");
const { parsePrice } = await import("../src/pages/admin/prices.ts");
const { fmtDateTime, dateOnly } = await import("../src/lib/format.ts");

test("B1: the switch confirm says the old plan ends at once and isn't refunded, also monthly to yearly on the same plan", () => {
  assert.equal(switchEndsNote("Pro"), "Your current Pro plan ends as soon as the new one is active. The unused time on it is not refunded.");
  const plans = src("pages/PlansPage.tsx");
  assert.match(plans, /paid !== "free" && me && !given \? ` \$\{switchEndsNote\(planName\(paid as PlanId\)\)\}`/);   // no same-plan exception
  assert.doesNotMatch(plans, /stops billing once the new one is active/);
});

test("B2: a currency charged by its own plan names that currency's amount, with no rupees or GST", () => {
  assert.equal(paymentWindowLine("Pro", "month", "USD"), 'The payment window that opens next is headed "StratLab · Pro, monthly" and shows the amount in USD.');
  assert.match(paymentWindowLine("Pro", "month", "INR"), /in rupees\.$/);
  assert.match(paymentWindowLine("Pro", "month"), /in rupees\.$/);
  const plans = src("pages/PlansPage.tsx");
  assert.match(plans, /if \(own\) return `\$\{money\(row,/);
  assert.ok(plans.indexOf("if (own) return") < plans.indexOf("rupeeCharge(rupees(p, period), gst)"));
});

test("B3: Account and the connection check name the real plan; the badge alone keeps (launch offer)", () => {
  const me = { plan: "pro", paid_plan: "free", plan_info: { name: "Pro" } };
  assert.equal(planLabel(me), "Free");
  assert.equal(planLabel({ ...me, paid_plan: "basic" }), "Basic");
  // Basic earned through invites is the plan they have (paid_plan stays "free"); the launch offer still shows the paid one
  const invited = { plan: "basic", paid_plan: "free", plan_info: { name: "Basic" }, free_basic_until: "2026-12-01", promo: null };
  assert.equal(planLabel(invited), "Basic");
  assert.equal(planLabel({ ...invited, plan: "pro", promo: { until: "2026-10-22" } }), "Free");
  const acc = src("pages/AccountPage.tsx");
  assert.doesNotMatch(acc, /<dd>\{me\.plan_info\.name\}/);
  assert.match(acc, /<dd>\{planName\}<\/dd>/);
  assert.match(acc, /\{planName\}\{me\.promo \? " \(launch offer\)"/);
  const set = src("pages/SettingsPage.tsx");
  assert.match(set, /\$\{planLabel\(me\)\} plan, \$\{u\.backtests_used\} Backtests this month/);
  assert.doesNotMatch(set, /experiments this month/);
});

test("B4: View as takes the real billing actions off Account", () => {
  const base = { plan: "basic", paid_plan: "basic", billing: { given_by_owner: false, cancel_at_period_end: false, renews_or_ends: "2026-11-01" } };
  assert.equal(planRun(base), "renews");
  assert.equal(planRun({ ...base, view_as: "basic" }), "viewing");
  assert.equal(planRun({ ...base, plan: "free", paid_plan: "free", view_as: "free" }), "free");
  assert.equal(planRow({ ...base, view_as: "basic" }), null);
  assert.match(src("pages/AccountPage.tsx"), /run === "viewing" \? <>.*viewingPlansNote\(/);
  assert.match(viewingPlansNote("Basic"), /^You're viewing as Basic\./);
});

test("B5: a paying user's plan can't be saved from Admin, and the server's words are shown", () => {
  const d = src("pages/admin/UserDialog.tsx");
  assert.match(d, /PAYS_RAZORPAY = "Cancel their subscription in Razorpay first, then change the plan\."/);
  assert.match(d, /\{user\.paying && <Notice tone="warn">\{PAYS_RAZORPAY\}<\/Notice>\}/);
  assert.match(d, /disabled=\{busy \|\| user\.paying\}/);
});

test("B6: the Users list says ends, not renews, for a cancelled subscription", () => {
  const u = { plan: "basic", plan_until: "2026-11-04T06:20:24+00:00", paying: true };
  assert.equal(planNote(u), "Razorpay · renews 4 Nov 2026");
  assert.equal(planNote({ ...u, cancel_at_period_end: true }), "Razorpay · ends 4 Nov 2026");
  assert.equal(planNote({ ...u, paying: false, cancel_at_period_end: true }), "Given · until 4 Nov 2026");
});

test("B7: a price is a number or empty (Automatic); anything else is refused", () => {
  assert.equal(parsePrice(""), null);
  assert.equal(parsePrice("  "), null);
  assert.equal(parsePrice(undefined), null);
  assert.equal(parsePrice("8"), 8);
  assert.equal(parsePrice("1,999.50"), 1999.5);
  for (const bad of ["abc", "8$", "$8", "1.2.3", "-5", "0", "1e3", "NaN"]) assert.equal(parsePrice(bad), undefined, bad);
  const p = src("pages/admin/PricesPanel.tsx");
  assert.match(p, /if \(Object\.keys\(bad\)\.length\) return;/);
  assert.match(p, /role="alert"/);
});

test("B9: each Admin panel that reads on open shows an error with Try again, not a placeholder for ever", () => {
  for (const f of ["EmailSection", "UsersSection", "StoragePanel", "InvoiceAdminPanel"]) {
    const s = src(`pages/admin/${f}.tsx`);
    assert.match(s, /ErrorState/, f);
    assert.match(s, /label: "Try again"/, f);
  }
  assert.equal([...src("pages/admin/UsersSection.tsx").matchAll(/label: "Try again"/g)].length, 3);
});

test("B8: the invoice form clears state and GSTIN when the country isn't India", () => {
  assert.match(src("components/InvoicesCard.tsx"), /v === "IN" \? \{ \.\.\.b, country: v \} : \{ \.\.\.b, country: v, state: "", gstin: "" \}/);
});

test("smaller: Zerodha asks before disconnecting; plan interest can be retried; newsletter saves don't undo each other", () => {
  const z = src("components/ConnectedAccounts.tsx");
  assert.match(z, /onClick=\{\(\) => setAsking\(true\)\}>Disconnect<\/button>/);
  assert.match(z, /title="Disconnect Zerodha\?"/);
  const pi = src("lib/planInterest.ts");
  assert.match(pi, /if \(state && !state\.unread\)/);
  const n = src("components/NewslettersCard.tsx");
  assert.match(n, /setPrefs\(\(cur\) => \(cur && cur\[key\] === c \? \{ \.\.\.cur, \[key\]: before\[key\] \} : cur\)\)/);
  assert.doesNotMatch(n, /setPrefs\(before\)/);
});

test("smaller: admin times carry a zone, admin invoice dates use the app's format, Open and Stop name their row", () => {
  assert.match(fmtDateTime("2026-10-15T08:30:00Z", { seconds: true, zone: true, tz: "Asia/Kolkata" }), /^15 Oct 2026, 14:00:00 IST$/);
  assert.equal(dateOnly("2026-10-15"), "15 Oct 2026");
  assert.match(src("pages/admin/SystemSection.tsx"), /fmtDateTime\(x\.at, \{ seconds: true, zone: true \}\)/);
  assert.match(src("pages/admin/InvoiceAdminPanel.tsx"), /dateOnly\(r\.date\)/);
  assert.match(src("pages/admin/InvoiceAdminPanel.tsx"), /aria-label=\{`Open invoice \$\{r\.number\}`\}/);
  assert.match(src("components/InvoicesCard.tsx"), /aria-label=\{`Open invoice \$\{r\.number\}`\}/);
  assert.match(src("pages/admin/UsersSection.tsx"), /aria-label=\{`Stop \$\{s\.name\}/);
});
