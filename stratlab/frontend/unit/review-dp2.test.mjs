// 25 Oct 2026, the deep audit of the plan locks and limits on the Money pages, the lock wording everywhere, the alerts form,
// notifications, Account's usage panel and the invite page (DP2-003 .. DP2-037, with DP1-007, DP1-018, DP1-023, DP1-024): a
// locked figure is "–" with the lock, one lock wording with the line icon, locked choices marked and explained when picked,
// Plans and the pages saying the same, and every kept limit on Account.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };     // lib/alerts.ts reads the config
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const L = await import("../src/lib/lockText.ts");
const plans = await import("../src/lib/plans.ts");
const offer = await import("../src/lib/offer.ts");
const { farLevel } = await import("../src/lib/alerts.ts");
const acct = await import("../src/lib/account.ts");
const inv = await import("../src/lib/invite.ts");

test("DP2-003: a locked lot count is '–' with the lock, never 0", () => {
  const p = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(p, /open_lt: \{ lots: number; gains: number; losses: number; with_gain: number \} \| null; soon_counts: Record<string, number> \| null;/);
  assert.match(p, /const lockedStat = \(label: string\) => <Stat label=\{label\} value=\{<span aria-label=\{`\$\{label\}: on the Pro plan`\}><Lock \/>–<\/span>\} note="on the Pro plan" \/>;/);
  assert.match(p, /\{v\.open_lt \? <Stat label="Open long-term lots"[\s\S]*?: lockedStat\("Open long-term lots"\)\}/);
  assert.match(p, /\{v\.soon_counts \? <Stat label="Turning long-term soon"[\s\S]*?: lockedStat\("Turning long-term soon"\)\}/);
});

test("DP2-004, DP2-012, DP2-013: Tax tools words each tab's lock at its top; reminders locked on Free; past dates marked", () => {
  const p = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(p, /<div className="k-page" data-plan-notes="own">/);
  assert.match(read("src/components/PageLock.tsx"), /main \.plan-note:not\(\.page-lock\), main \[data-plan-notes\]/);
  // DH-021 reworded the advance tax lock to what Pro adds (the shares of the tax are shown on every plan)
  for (const note of ["Dividends by company, with the TDS expected", "the amount still due by each date", "Each open lot's long-term gain"]) assert.equal(p.split(note).length - 1, 1, note);
  assert.match(p, /\{v\.remind_locked\s*\? <p className="k-small k-muted" data-testid="advance-remind-locked">/);
  assert.match(p, /<FieldGroup label="Reminders" infoLabel="About advance tax reminders"/);
  assert.match(p, /\{d\.date < today \? <span className="k-note"> · passed<\/span> : d\.n === nextDue \? <span className="k-note"> · next<\/span> : null\}/);
  assert.match(p, /<h3 className="k-sub">Assumptions<\/h3>\s*<ul className="k-list">\{v\.assumptions/);
});

test("DP2-022, DP1-018: one limit wording, with the month's reset and what the next plan gives", () => {
  const oct = Date.parse("2026-10-25T06:00:00Z");
  assert.equal(L.resetDay(oct), "1 Nov");
  assert.equal(L.resetDay(Date.parse("2026-12-31T20:00:00Z")), "1 Feb");               // already January in India
  assert.deepEqual(L.limitLine("free", "stock_alerts", "Your Free plan has 5 alerts on at a time. Delete one to add another", "alerts"),
    { text: "Your Free plan has 5 alerts on at a time. Delete one to add another. Basic gives 25.", next: "basic" });
  assert.deepEqual(L.limitLine("basic", "screens", "Your Basic plan keeps 10 saved screens. Delete one to save another", "screens"),
    { text: "Your Basic plan keeps 10 saved screens. Delete one to save another. Pro gives 25.", next: "pro" });
  assert.equal(L.limitLine("pro", "stock_alerts", "Your Pro plan has 100 alerts on at a time", "alerts").next, null);
  assert.equal(L.limitLine("basic", "backtests_per_month", "You've used all 100 backtests this month", "backtests", true, oct).text,
    "You've used all 100 backtests this month. The count starts again on 1 Nov. Pro has no limit on backtests.");
  assert.deepEqual(L.nextPlan("free", "networth_items"), { id: "basic", name: "Basic", cap: null });
  // the lock's button says See plans, so the words never say it again; a tooltip without a button still does
  const paid = { mode: "paid", payments: true, yearly: true, promo_until: null, free_now: {}, free_trial_days: null };
  assert.equal(offer.unlockHint(paid, undefined, "Basic is ₹699 a month."), "Basic is ₹699 a month.");
  assert.match(offer.featureTag("basic", paid, { canUse: false }).why, /See the plans to upgrade\.$/);
  // the alerts page and the screens page use it; "see plans" is never in the words
  const alerts = read("src/pages/AlertsPage.tsx");
  assert.match(alerts, /limitLine\(plan, "stock_alerts", `Your \$\{me\?\.plan_info\.name \?\? "plan"\} plan has \$\{page\.limit\} alert/);
  assert.doesNotMatch(alerts, /That's all your plan has|see plans for more/);
  assert.match(read("src/pages/Screens.tsx"), /limitLine\(planIdOf\(me\?\.plan\), "screens"/);
  assert.doesNotMatch(read("src/pages/Screens.tsx"), /or <Link className="link" to="\/plans">see plans<\/Link>/);
  // a 402's toast adds the plan's price in the visitor's currency
  assert.match(read("src/lib/app.tsx"), /if \(canBuy\(offer\.current\) && err\.plan\) void planPriceFor\(err\.plan\)\.then\(\(p\) => show\(p \? `\$\{err\.message\} \$\{p\}` : err\.message\)\);/);
  assert.match(read("src/lib/api.ts"), /if \(d\?\.plan === "basic" \|\| d\?\.plan === "pro"\) e\.plan = d\.plan;/);
});

test("DP2-012, DP1-018, DP1-025: the lock is the line icon, never the emoji; the page lock reads plainly", () => {
  for (const f of ["src/components/kit/Notice.tsx", "src/components/PageLock.tsx", "src/lib/offer.ts", "src/pages/NotebookPage.tsx", "src/pages/OptionsPage.tsx", "src/styles.css"])
    assert.doesNotMatch(read(f), /🔒/, f);
  assert.match(read("src/components/Icons.tsx"), /export const Lock = /);
  assert.match(read("src/components/kit/Notice.tsx"), /<span className="plan-lock" aria-hidden="true"><Lock \/><\/span>/);
  assert.match(read("src/components/PageTags.tsx"), /\{tag\.locked && <Lock size=\{12\} \/>\}\{tag\.label\}/);
  assert.match(read("src/styles.css"), /\.side-lock::before \{ content: ""; display: inline-block;[^}]*mask: var\(--lock-mask\)/);
  assert.equal(L.lockWords("Market breadth history, charts and sector table", "Basic", "Free", false),
    "Basic adds market breadth history, charts and sector table. Everything else here is on your Free plan.");
  assert.equal(L.lockWords("ITR-ready schedules and a PDF pack for your CA", "Pro", "Basic", false),
    "Pro adds ITR-ready schedules and a PDF pack for your CA. Everything else here is on your Basic plan.");
  assert.equal(L.lowerFirst("SIP test: dip rules"), "SIP test: dip rules");
  assert.doesNotMatch(read("src/components/PageLock.tsx"), /the rest of the page is yours/);
  // each money flag says the Free limit it lifts (the Mutual funds lock didn't name the 5 funds)
  const flag = (k) => plans.FLAGS.find(([f]) => f === k)[1];
  assert.equal(flag("mf_gains"), "Every mutual fund scheme (Free keeps 5) and capital gains by year");
  assert.equal(flag("networth"), "Every net worth entry (Free keeps 5) and the monthly history");
});

test("DP2-009, DP2-010: Plans says what the Money pages lock and what they show to everyone", () => {
  const flag = (k) => plans.FLAGS.find(([f]) => f === k)[1];
  assert.match(flag("filings"), /each holding's red flags, recent filings and results date on My Holdings/);
  assert.match(flag("dividends"), /^Dividends by company on Tax tools/);
  assert.match(flag("us_tax"), /sale by sale/);
  const every = plans.EVERYONE.join(" | ");
  assert.match(every, /Each holding's dividends on My Holdings/);
  assert.match(every, /each year's US share gains in rupees/);
  assert.match(every, /A preview of the ITR-ready export: each schedule's totals and line counts/);
  assert.match(every, /Weekly Market Brief and My Stocks emails/);
  assert.match(plans.FEATURES.free.join(" "), /the weekly Market Brief and My Stocks emails/);
  // the Holdings card says "Basic for part"
  assert.match(read("src/lib/nav.ts"), /flag: "filings", part: true \}\),/);
  assert.match(read("src/components/PageTags.tsx"), /const part = gate \? gate\.whole === false : !!page\.part;/);
  assert.match(read("src/pages/HoldingsPage.tsx"), /Each holding's red flags, recent filings and results date are on the \{facts\.filings_plan\} plan/);
});

test("DP2-011: the ITR downloads look alike and say why they're off", () => {
  const p = read("src/pages/money/ItrExportPage.tsx");
  assert.match(p, /<button key=\{f\} type="button" className="btn outline" disabled=\{v\.locked/);
  assert.doesNotMatch(p, /f === "pdf" \? "" : " quiet"/);
  assert.match(p, /\{v\.locked && <div id="itr-why-off"><PlanNote>Part of this page is on the \{v\.plan\} plan\./);       // the lock is said once (RC2B-017)
});

test("DP2-014: Money's home cards carry their plan tags and read in full on a phone", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /\{at && <PageTags page=\{at\.page\} \/>\}<\/Link>;/);
  assert.match(read("src/styles.css"), /\.money-cards \.explore-card \.small \{ display: block; -webkit-line-clamp: unset; overflow: visible; \}/);
});

test("DP2-020, DP1-007: locked alert kinds and indicators are marked, and picking one says why with the price", () => {
  const f = read("src/components/AlertForm.tsx");
  assert.match(f, /label: plan \? `\$\{x\.label\} \(\$\{plan === "pro" \? "Pro" : "Basic"\}\)` : x\.label/);
  assert.match(f, /\{locked \? <div className="k-form-wide"><PlanNote plan=\{locked === "pro" \? "pro" : "basic"\}>/);
  assert.match(f, /disabled=\{busy \|\| !!locked\}/);
  const r = read("src/components/Rules.tsx");
  assert.match(r, /<option key=\{i\.t\} value=\{i\.t\}>\{i\.name\}\{i\.pro && !allIndicators \? " \(Basic\)" : ""\}<\/option>/);
  assert.match(r, /if \(ind\?\.pro && !allIndicators && t !== value\.t\) \{ setAskedFor\(ind\.name\); return; \}/);
  assert.match(r, /\{askedFor && <div data-testid="indicator-locked"><PlanNote plan="basic">\{askedFor\} is on the Basic plan/);
});

test("DP2-023, DP1-023, DP2-024: plain 'Sent by', no address printed, a far level noticed, the form in a pop-up, Stage's own words", () => {
  const a = read("src/pages/AlertsPage.tsx");
  assert.match(a, /: "This page only"\}/);
  assert.doesNotMatch(a, /: "Nowhere yet"|confirmed \{page\.email\}/);
  assert.match(a, /<Modal title=\{full \? "Your alerts are full" : "New alert"\}/);
  assert.match(a, /page\.active\.length > FIND_FROM \?/);
  assert.equal(farLevel(99999, 1190), "That level is 84 times the last price. Check it before you set the alert.");
  assert.equal(farLevel(1300, 1190), null);
  assert.equal(farLevel(100, 1190), "That level is 92% below the last price. Check it before you set the alert.");
  assert.equal(farLevel(5000, null), null);
  assert.match(read("src/components/AlertForm.tsx"), /: c\.kind === "stage"\s*\/\/[^\n]*\n\s*\? "Checked during market hours on the daily candles/);
});

test("DP2-030: the daily report isn't shown ticked on Free; an empty email box says where alerts go; Daily explains itself", () => {
  const s = read("src/components/AlertSettings.tsx");
  assert.match(s, /<CheckField checked=\{canReport && alerts\.daily\} disabled=\{!canReport\}/);
  assert.match(s, /hint=\{!alerts\.email\.trim\(\) && me\.email \? "Empty: alerts go to the email you sign in with\." : undefined\}/);
  assert.match(s, /k-hint-line k-form-wide" data-testid="alert-where"/);
  const n = read("src/components/NewslettersCard.tsx");
  assert.match(n, /if \(plan\) \{ setAsked\(\{ key, plan \}\); return; \}/);
  assert.match(n, /disabled: busy === key \};/);
});

test("DP2-031: Account lists every kept limit and the trial's days left", () => {
  assert.deepEqual(acct.keptRow({ key: "stock_alerts", used: 3, limit: 5, next: "Basic" }), ["Stock alerts on", "3 of 5"]);
  assert.deepEqual(acct.keptRow({ key: "networth_items", used: 12, limit: null, next: null }), ["Net worth entries", "12 (no limit)"]);
  assert.deepEqual(acct.keptRow({ key: "journal_trades", used: null, limit: 50, next: "Basic" }), ["Trades the journal counts", "The last 50"]);
  assert.equal(acct.keptRow({ key: "unknown", used: 1, limit: 1, next: null }), null);
  const me = { plan: "free", view_as: null, live_running: 0, live_limit: 1 };
  assert.equal(acct.trialUse({ ...me, trial: { started: false, active: false, ends_at: null, available: true, days: 5, days_left: 5 } }),
    "0 of 1 · trial: 5 market days from your first start");
  assert.equal(acct.trialUse({ ...me, trial: { started: true, active: true, ends_at: "2026-10-30T18:30:00+00:00", available: true, days: 5, days_left: 3 } }),
    "0 of 1 · trial: 3 market days left, until 30 Oct");
  assert.equal(acct.trialUse({ ...me, trial: { started: true, active: false, ends_at: "2026-10-30T18:30:00+00:00", available: false, days: 5 } }),
    "0 of 1 · trial ended on 30 Oct");
  const p = read("src/pages/AccountPage.tsx");
  assert.match(p, /api<\{ rows: KeptLimit\[\] \}>\("\/me\/limits"\)/);
  assert.match(p, /row\[0\] === "Given by StratLab" \? \[row\[0\], `\$\{row\[1\]\}\. Nothing renews and there's nothing to cancel\.`\]/);
});

test("DP2-034, DP2-035: My stocks says what starts it; the invite page says its title once, and is linked from Account", () => {
  assert.match(read("src/pages/NewsPage.tsx"), /tab === "mine"\s*\? <Card><EmptyState title="No My Stocks briefs yet" action=\{\{ label: "Add to your watchlist", to: "\/research" \}\}>/);
  const i = read("src/pages/InvitePage.tsx");
  assert.match(i, /<CardHead title="Friends and free time"/);
  assert.equal(i.split('label="Your invite link"').length - 1, 1);
  assert.match(i, /<ul className="k-list">\{youGetLines\(v, paid\)/);
  const lines = inv.youGetLines({}, "basic");
  assert.equal(lines.length, 4);
  assert.equal(lines[3], "You're on Basic, so it's kept for you and starts only if your Basic plan stops.");
  assert.match(read("src/pages/AccountPage.tsx"), /<Link to="\/invite" className="btn outline sm">Your invite link<\/Link>/);
});
