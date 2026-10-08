// Round 5, the owner's review (R5O-…): the frontend side of the fixes.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a failed /me shows Retry, never a spinner that waits forever (R5O-002)", () => {
  const main = read("src/main.tsx");
  assert.match(main, /StratLab couldn't load your account: \{meError\}<\/span><AccountRetry \/>/);
  assert.doesNotMatch(main, /if \(!me\) return <Loading label="Checking access" \/>/);
  assert.match(main, /<AccountWait label="Checking access" \/>/);
  const wait = read("src/components/AccountWait.tsx");
  assert.match(wait, /if \(!meError\) return <Skeleton/);
  assert.match(wait, /label: busy \? "Trying again…" : "Retry"/);
  for (const p of ["src/pages/AdminPage.tsx", "src/pages/AccountPage.tsx", "src/pages/SettingsPage.tsx"])
    assert.match(read(p), /<AccountWait label=/, p);
  // one quiet second try on a 502/503/504 or no answer before the error shows
  assert.match(read("src/lib/app.tsx"), /e\.status !== 503 && e\.status !== 502 && e\.status !== 504\) throw e;/);
});

test("notebook defaults invent nothing, and the sell question stays (R5O-010)", () => {
  const rules = read("src/lib/rules.ts");
  assert.match(rules, /const DEFAULT_RISK: Risk = \{[^}]*tgt: 0,/);
  assert.match(read("src/components/IdeaComposer.tsx"), /strategy: withDefaultExit\(strategy, out\.mentioned \|\| \[\]\)/);
  assert.match(read("src/components/ImportStrategy.tsx"), /\{ \.\.\.s\.risk, sl: 0, tgt: 0, \.\.\.\(out\.risk \|\| \{\}\) \}/);
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /body: \{ gaps: g \}/);                       // the questions are saved with the notebook
  assert.match(page, /body: \{ clearGaps: true \}/);
  assert.match(page, /No sell rule is set:/);
  assert.match(page, /const DEFAULT_DAILY_DAYS = 1825;/);         // "years of real prices": 5 years by default
  assert.doesNotMatch(page, /useState\("365"\)/);
  const r = read("src/components/Rules.tsx");
  // the exit's add button opens a picker, and sits under the block's rules like the entry's
  assert.doesNotMatch(r, /addBtn\("exit"/);
  assert.match(r, /<Pop title=\{label\} label=\{`\+ \$\{label\}`\} cls="add-rule" plain>/);
  const exitBlock = r.slice(r.indexOf('<Block title="Exit"'), r.indexOf('<Block title="Size and candles">'));
  assert.ok(exitBlock.indexOf('exitPick("exit"') > exitBlock.indexOf('title="Target"'), "add button under the stop and target line");
  const gaps = read("src/components/Gaps.tsx");
  assert.match(gaps, /label: hasExit \? "No target, let the sell rule decide" : "No target", rec: true/);
});

test("library cards: facts about the checks, buy and hold beside the return, which check didn't run (R5O-014)", async () => {
  const { checksLine } = await import("../src/lib/tradeUi.ts");
  assert.equal(checksLine(3, 3, ["nearby settings"]), "3 of 4 checks passed · nearby settings not run");
  assert.equal(checksLine(3, 3), "3 of 4 checks passed · 1 not run");
  const lib = read("src/pages/LibraryPage.tsx");
  assert.match(lib, /<VerdictBadge v=\{e\.verdict\.verdict\} facts \/>/);
  assert.doesNotMatch(lib, /<VerdictBadge v=\{e\.verdict\.verdict\} \/>/);
  assert.match(lib, /<HoldLine e=\{e\} \/>/);
  assert.match(lib, /\{num\(gap, 1\)\} points \{h\.gap < 0 \? "behind" : "ahead"\}/);
  assert.match(lib, /lede=\{onlyOurs \?/);
  const ui = read("src/components/ui.tsx");
  assert.match(ui, /edge: "Passed the checks"/);
  for (const p of ["src/pages/Login.tsx", "src/pages/SpaceHomes.tsx", "src/pages/LibraryPage.tsx"])
    assert.doesNotMatch(read(p), /Rules others published/, p);
});

test("Admin's 'Needs your attention' lists feeds on Check and each AI provider that can't answer, with its reason (R5O-016)", async () => {
  const { attention, aiUp } = await import("../src/pages/admin/attention.ts");
  const ai = [
    { label: "Groq", configured: true, in_use: true, model: "m", last_error: null, answering: true, state_text: "Working." },
    { label: "OpenRouter", configured: true, in_use: true, model: "m", last_error: "rate limited (429: slow down)", answering: true, state_text: "Working; rate limited" },
    { label: "Vercel AI Gateway", configured: true, in_use: true, model: "m", last_error: "x", answering: false,
      state_text: "The key was rejected: the account needs a payment method on file (403: AI Gateway requires a valid credit card on file)" },
  ];
  assert.equal(ai.filter(aiUp).length, 2);
  assert.equal(aiUp({ last_error: "old server", quota: false }), false);          // an older server: the last error decides
  const ov = { server: { kite_ready: true, feed_connected: true, live_sessions: 0, auto_login_configured: true, auto_login: { ok: true, message: "ok" },
    ai, billing_enabled: true }, stats: {} };
  const jobs = [
    { id: "positioning", name: "Positioning", schedule: "Trading days", last_run: null, error: null, state: "warn" },
    { id: "corp", name: "Corporate actions", schedule: "7:20 AM", last_run: null, error: null, state: "warn" },
    { id: "option-chains", name: "Option chain recording", schedule: "Off", last_run: null, error: null, state: "warn" },
    { id: "etf", name: "ETF", schedule: "x", last_run: "2026-10-08T09:00:00Z", error: null, state: "ok" },
  ];
  const items = attention(ov, null, jobs).map((a) => a.text);
  assert.ok(items.includes("2 data feeds on Check: Positioning (not run yet), Corporate actions (not run yet)."), items.join("\n"));
  assert.ok(items.some((t) => t.startsWith("AI, Vercel AI Gateway: The key was rejected: the account needs a payment method on file (403:")), items.join("\n"));
  assert.ok(!items.some((t) => t.includes("OpenRouter")));
});

test("no data provider's name on the company and lending pages (R5O-020)", () => {
  const page = read("src/pages/Research.tsx");
  assert.doesNotMatch(page, /More on Wikipedia|From Wikipedia/);
  assert.match(page, /Read the full entry ↗/);
  assert.doesNotMatch(read("src/pages/StockLendingPage.tsx"), /bhavcopy/i);
  // a headline with no publisher shows its time alone, without a stray " · "
  assert.match(read("src/components/Research.tsx"), /\{\[n\.source, n\.at \? ago\(n\.at\) : null, old\]\.filter\(Boolean\)\.join\(" · "\)\} ↗/);
});

test("the scan page counts what it skipped and words a one-candle rule properly (R5O-023)", () => {
  const p = read("src/pages/ResearchScans.tsx");
  assert.doesNotMatch(p, /any of the last \{scan\.within\} candle\{/);
  assert.match(p, /"Counts as a match when it held on the latest candle\."/);
  assert.match(p, /`\$\{preset\.checked\} of \$\{preset\.asked\}`/);
  assert.match(p, /skipped, named below/);
});

test("Ctrl K: a feature's name beats a company's letters, no futures for a plain stock, no ideas for nonsense (R5O-024)", async () => {
  const { namesFeature, asksContract, offerIdeas } = await import("../src/lib/paletteRank.ts");
  const { match } = await import("../src/lib/features.ts");
  assert.ok(match("sip", 5).some((f) => namesFeature(f.title, "sip")), "sip names Test a SIP");
  assert.ok(match("tax", 5).some((f) => namesFeature(f.title, "tax")), "tax names a tax feature");
  assert.ok(!namesFeature("Test a SIP", "si"));
  assert.ok(!asksContract("tcs") && asksContract("tcs fut") && asksContract("TCS26OCTFUT") && asksContract("nifty 22000 ce"));
  assert.equal(offerIdeas("zzzzqq", { features: 0, companies: 0, helps: 0, intent: false }), false);
  assert.equal(offerIdeas("momentum ideas for banks", { features: 0, companies: 0, helps: 0, intent: false }), true);
  assert.equal(offerIdeas("tcs", { features: 0, companies: 1, helps: 0, intent: false }), true);
  const p = read("src/components/SearchPalette.tsx");
  assert.match(p, /!isCompany\(i\) && \(!i\.fno \|\| asksContract\(text\) \|\| !companies\.length\)/);
  assert.match(p, /if \(companies\.length && \(companies\[0\]\.match \?\? 9\) <= STRONG && !exactFeature && !intent\) first\("Companies"\);/);
});

test("My space greets in India's time for the Indian market, or the person's own zone (R5O-031)", async () => {
  const { greetingZone, hourIn, greetingAt } = await import("../src/lib/greeting.ts");
  assert.equal(greetingZone("IN", "UTC"), "Asia/Kolkata");
  assert.equal(greetingZone("IN", "Europe/London"), "Asia/Kolkata");
  assert.equal(greetingZone("US", "America/New_York"), "America/New_York");
  assert.equal(greetingZone("US", "Etc/UTC"), "Asia/Kolkata");
  const at = new Date("2026-10-08T08:57:00Z");                    // 14:27 IST, the review's "Good morning"
  assert.equal(greetingAt(hourIn("Asia/Kolkata", at)), "Good afternoon");
  assert.equal(greetingAt(hourIn("UTC", at)), "Good morning");
  assert.doesNotMatch(read("src/pages/MineHome.tsx"), /new Date\(\)\.getHours\(\)/);
});

test("the theme map says a company without a checked ticker isn't listed, not 'private' (R5O-008)", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /\{co\.name\} \(not listed\)/);
  assert.doesNotMatch(r, /\(private\)/);
});
