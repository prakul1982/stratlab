// FREE-TIER (owner, Nov: Free is a teaser): the plan copy says Free's smaller limits from LIMITS, the deck lock reads well for a limit of 0,
// Account and the deep dive never say "0 of 0", the refresh button on Free says where refreshes are, the tax report's downloads are Basic's,
// and the one-time notice for an account made before the change says exactly what changes and when.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const plans = await import("../src/lib/plans.ts");
const { FEATURES, EVERYONE } = await import("../src/lib/planFeatures.ts");
const acct = await import("../src/lib/account.ts");
const fc = await import("../src/lib/freeChange.ts");
const usage = await import("../src/lib/usageText.ts");
const gates = await import("../src/lib/gates.ts");
const L = await import("../src/lib/lockText.ts");

test("Free's limits are the teaser ones; Basic and Pro are as before", () => {
  const f = plans.LIMITS.free;
  assert.deepEqual([f.backtests_per_month, f.ai_builds_per_month, f.group_size, f.deepdives_per_month, f.decks_per_month, f.stock_alerts, f.screens, f.themes_per_month, f.ai_reads_per_day],
    [5, 5, 5, 1, 0, 3, 1, 1, 5]);
  const b = plans.LIMITS.basic, p = plans.LIMITS.pro;
  assert.deepEqual([b.backtests_per_month, b.deepdives_per_month, b.decks_per_month, b.stock_alerts, b.screens, b.ai_reads_per_day, b.themes_per_month], [100, 15, 5, 25, 10, 60, 10]);
  assert.deepEqual([p.backtests_per_month, p.decks_per_month, p.ai_reads_per_day, p.themes_per_month], [null, null, null, null]);
  assert.equal(plans.planOf("tax_export"), "basic");
});

test("the Free card says its numbers from LIMITS and never '0 slide deck'", () => {
  const card = plans.KEY.free.join(" | ");
  assert.match(card, /5 backtests and 5 AI strategy builds a month/);
  assert.match(card, /1 company deep dive a month, 5 fresh AI reads a day/);
  assert.match(card, /3 stock alerts, 1 saved screen, 30 holdings/);
  assert.doesNotMatch(card, /\b0 slide deck|1 saved screens/);
  const all = FEATURES.free.join(" | ");
  assert.match(all, /1 company deep dive a month with the report card and checklist, 5 fresh AI reads a day, and the sample deck to download/);
  assert.match(all, /every theme already mapped \(and 1 new theme a month\)/);
  assert.match(all, /3 stock alerts and 1 saved screen;/);
  assert.match(FEATURES.basic.join(" "), /Money: tax report downloads, /);
  assert.match(FEATURES.basic.join(" "), /15 company deep dives, 5 slide decks and 10 new themes a month/);
});

test("the table has the new themes row and the tax downloads row, and the for-everyone list says what stays open", () => {
  assert.ok(plans.NUMBERS.some(([k, label]) => k === "themes_per_month" && label === "New themes mapped a month"));
  assert.ok(plans.FLAGS.some(([k, label]) => k === "tax_export" && /Tax report downloads: CSV and PDF/.test(label)));
  assert.equal(plans.FLAG_GROUP.tax_export, "money");
  assert.ok(EVERYONE.includes("Every theme already mapped"));
  assert.ok(EVERYONE.some((x) => /the tax report on screen/.test(x)));
  // the comparison table's cell for Free's decks
  assert.match(read("src/components/PlanCompare.tsx"), /v === 0 && k === "decks_per_month" \? "0 \(a sample deck to download\)"/);
  // the landing page's JavaScript doesn't carry the for-everyone list any more (the table loads it with itself)
  assert.doesNotMatch(read("src/lib/plans.ts"), /export const EVERYONE/);
});

test("the deck lock reads well for a limit of 0, as the server's words", () => {
  assert.equal(acct.deckLock(), "Slide decks are on Basic: 5 a month. The sample deck on the Plans page shows what one holds.");
  const line = acct.deepDiveLimitLine(1, 1, 0, 0);
  assert.equal(line, "Companies opened this month: 1 of 1 (limit reached). Slide decks are on Basic: 5 a month. The sample deck on the Plans page shows what one holds. Opening a company again this month doesn't count.");
  assert.doesNotMatch(line, /0 of 0/);
  // Basic's line as before
  assert.match(acct.deepDiveLimitLine(3, 15, 1, 5), /Decks: 1 of 5; a company's or a theme's PDF and PowerPoint are one deck\./);
  assert.equal(acct.noneOnPlan("Free", "Basic", 5, "The sample deck is on Plans."), "None on Free: on Basic, 5 a month. The sample deck is on Plans.");
  // the locked buttons: on the deep dive and the theme page, with the sample deck beside them
  for (const f of ["src/pages/DeepDive.tsx", "src/components/ThemeDive.tsx"]) {
    const src = read(f);
    assert.match(src, /deck_limit === 0/);
    assert.match(src, /data-testid="deck-locked">🔒 Slides: on Basic<\/Link>/);
    assert.match(src, /<SampleDeckLink className="btn quiet sm" label="Sample deck" \/>/);
  }
  assert.match(read("src/pages/PlansPage.tsx"), /Slide decks are on Basic and Pro\. <SampleDeckLink label="Download a sample deck" \/>/);
  assert.match(read("src/components/SampleDeck.tsx"), /\/pricing\/sample-deck\/info/);
});

test("the next-plan wording for Free's new counts", () => {
  assert.deepEqual(L.nextPlan("free", "themes_per_month"), { id: "basic", name: "Basic", cap: 10 });
  assert.deepEqual(L.nextPlan("free", "decks_per_month"), { id: "basic", name: "Basic", cap: 5 });
  assert.equal(L.limitLine("free", "backtests_per_month", "You've used all 5 backtests this month", "backtests").text, "You've used all 5 backtests this month. Basic gives 100.");
});

test("refresh on Free says it is on Basic, not 'back at midnight'", () => {
  // (updated on purpose: a Refresh is one fresh AI read, LIVE7B-002; Free's lack of it is the server's refresh_off, not a "refresh" row)
  const free = { plan: "Free", rows: [{ key: "research_ai", label: "Fresh AI reads", used: 0, limit: 5, left: 5, resets: "day" }], refresh_off: true };
  const basic = { plan: "Basic", rows: [{ key: "research_ai", label: "Fresh AI reads", used: 60, limit: 60, left: 0, resets: "day" }], refresh_off: false };
  assert.equal(usage.refreshNotOnPlan(free), true);
  assert.equal(usage.refreshNotOnPlan(basic), false);
  assert.equal(usage.REFRESH_ON_BASIC, "Refreshing a stored read is on Basic and Pro");
  assert.match(read("src/components/StoredStamp.tsx"), /\{off \? "On Basic" : none \? "None left today"/);
});

test("the tax report's downloads are Basic's: a lock banner on the page and a locked button", () => {
  assert.deepEqual(gates.gateFor("/tax-report"), { feature: "tax_export", whole: false });
  assert.equal(gates.gatePlan(gates.gateFor("/tax-report")), "basic");
  assert.equal(gates.PART_WORDS.tax_export, "the downloads");
  assert.match(gates.featureName("tax_export"), /^Tax report downloads/);
  assert.match(read("src/pages/TaxReportPage.tsx"), /me\?\.plan_info\?\.features\?\.tax_export !== false/);
  assert.match(read("src/pages/TaxReportPage.tsx"), /🔒 Downloads: on Basic/);
});

const NOTICE = {
  on: "2026-11-30T00:00:00+05:30",
  rows: [{ key: "ai_reads_per_day", label: "Fresh AI reads a day", before: 60, after: 5 },
    { key: "themes_per_month", label: "New themes mapped a month", before: null, after: 1 },
    { key: "decks_per_month", label: "Slide decks a month", before: 1, after: 0 },
    { key: "same", label: "Unchanged", before: 30, after: 30 }],
  moves: ["The tax report's CSV and PDF downloads move to Basic (the report on screen stays free)"],
};

test("the one-time notice says exactly what changes and when", () => {
  assert.equal(fc.changeTitle(NOTICE), "Your Free plan changes on 30 Nov 2026");
  assert.deepEqual(fc.changeLines(NOTICE), [
    "Fresh AI reads a day: 60 now, 5 from 30 Nov 2026",
    "New themes mapped a month: no limit now, 1 from 30 Nov 2026",
    "Slide decks a month: 1 now, 0 from 30 Nov 2026",
    "The tax report's CSV and PDF downloads move to Basic (the report on screen stays free), from 30 Nov 2026",
  ]);
  assert.equal(fc.changeSeenKey(NOTICE), "stratlab:free-change-seen:2026-11-30");
  // on Account and on My space, once (a "Got it" kept on the device), and never emailed
  assert.match(read("src/pages/AccountPage.tsx"), /<FreeChangeNotice \/>/);
  assert.match(read("src/pages/MineHome.tsx"), /<FreeChangeNotice \/>/);
  const comp = read("src/components/FreeChangeNotice.tsx");
  assert.match(comp, /localStorage\.setItem\(key, "1"\)/);
  assert.match(comp, />Got it</);
});
