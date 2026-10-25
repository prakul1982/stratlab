// 25 Oct 2026, the deep audit of the builder, the plan limits and the locks on Free and Basic (DP1-001 .. DP1-028): no
// build charged for nothing, Basic's indicators refused by name on Free, the simple converter's rules shown for a yes,
// the limits said before the click, locked pages that show what they hold, and a shorter Plans page.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const R = await import("../src/lib/rules.ts");
const P = await import("../src/lib/paperText.ts");
const N = await import("../src/lib/notebookText.ts");
const plans = await import("../src/lib/plans.ts");
const { deepDiveLimitLine } = await import("../src/lib/account.ts");

test("DP1-001: the count of AI builds is read again after every try, made or not", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /} finally \{\n\s*\/\/ the count of builds left[^\n]*\n[^\n]*\n\s*refreshMe\(\);/);
  assert.doesNotMatch(src, /if \(r\.usedAI\) refreshMe\(\);/);
  assert.doesNotMatch(read("src/components/Rules.tsx"), /if \(out\.usedAI\) refreshMe\(\);/);
});

test("DP1-002, DP1-003: an idea on Basic's indicators is refused with the plan and its price, and the examples say Basic", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /if \(err\.code === "indicator_plan"\) return \{ built: null, usedAI: false, system: false, locked: true, note: err\.message \};/);
  assert.match(src, /\{note\}\{locked && basicPrice \? ` \$\{basicPrice\}` : ""\}/);            // "… Basic is $8 a month or $80 a year."
  assert.match(src, /locked \? <>\n\s*<PlanActions \/>/);
  // the two examples on Basic's indicators are tagged on Free, and picking one says so without a build
  assert.match(src, /basic: \[\n\s*`Short\$\{on\(a\)\} when the price falls below the lowest low/);
  assert.match(src, /data-testid="example-basic"> · Basic<\/span>/);
  assert.match(src, /if \(!allIndicators && me && ex\.basic\.includes\(idea\)\) \{/);
  // the converter's own Basic rules (the lowest low, Stage 2) are refused on Free too
  assert.match(src, /if \(fallback && opts\.allIndicators === false && usesPro\(strategy\)\) return \{ built: null, usedAI, system: false, locked: true/);
  const s = { ...R.blankStrategy(), entry: [{ l: { t: "price" }, op: "lt", r: { t: "dc_lower", p: 20 } }, { l: { t: "price" }, op: "gt", r: { t: "supertrend", p: 10, m: 3 } }] };
  assert.deepEqual(R.proNames(s), ["Lowest low of N candles", "Supertrend"]);
});

test("DP1-004: the simple converter's rules are shown for a yes, with the classic ideas beside them", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /usedAI, note: fallback, confirm: !!fallback,/);
  assert.match(src, /if \(r\.confirm\) \{ setNote\(r\.note\); setPending\(\{ built: r\.built, idea \}\); return; \}/);
  assert.match(src, /Build with these rules<\/button>/);
  assert.match(src, /Classic ideas \(no AI build\)/);
  assert.match(src, /The simple converter read your idea instead, and it can get an idea wrong, so check the rules it made\./);
  // from search, converter rules open in the notebook to be checked, never tested or traded unseen
  assert.match(read("src/components/SearchPalette.tsx"), /if \(!inst \|\| r\.confirm\) \{/);
  const s = { ...R.blankStrategy(), entry: [{ l: { t: "price" }, op: "xa", r: { t: "sma", p: 100 } }], exit: [{ l: { t: "price" }, op: "xb", r: { t: "sma", p: 100 } }] };
  assert.deepEqual(R.ruleLines(s), ["Buy when Price crosses above SMA 100", "Sell when Price crosses below SMA 100", "Stop loss 2% (a default: your words set none)"]);
  assert.deepEqual(R.ruleLines({ ...s, risk: { ...s.risk, sl: 3, trail: 5 } }, ["sl"]).slice(2), ["Stop loss 3%", "Trailing stop 5%"]);
  assert.equal(R.ruleLines({ ...s, entryJoin: "any", entry: [...s.entry, { l: { t: "rsi", p: 14 }, op: "lt", r: { t: "num", v: 30 } }] })[0],
    "Buy when Price crosses above SMA 100 or RSI 14 is below 30");
});

test("DP1-008: a library card says what a copy needs on the plan, before the copy", () => {
  const st = { ...R.blankStrategy(), entry: [{ l: { t: "price" }, op: "gt", r: { t: "supertrend", p: 10, m: 3 } }] };
  const free = { allIndicators: false, groupCap: 10, basicCap: 25, proCap: 50 };
  assert.equal(R.copyNeeds(st, 20, free), "Runs on Basic: it uses Supertrend, and its group of 20 is over your plan's 10. A copy is yours to edit on any plan.");
  assert.equal(R.copyNeeds(R.blankStrategy(), 30, free), "Runs on Pro: its group of 30 is over your plan's 10. A copy is yours to edit on any plan.");
  assert.equal(R.copyNeeds(st, 20, { ...free, allIndicators: true, groupCap: 25 }), null);
  assert.match(read("src/pages/LibraryPage.tsx"), /\{needs\(e\) && <span className="k-note" data-testid="lib-needs">\{needs\(e\)\}<\/span>\}/);
});

test("DP1-009, DP1-012: out of runs says when the count starts again and what the next plan gives; no Run before a market", () => {
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /\(limit reached\)\. The count starts again on \{resetDay\}\.\{moreRuns\}<\/PlanNote>/);   // as a plan note since DP2-022
  assert.match(nb, /\{!outOfRuns && \(inst \|\| group\) && <span className="k-small k-muted kbd-hint">/);
  assert.match(nb, /const currency = group \? \(market\?\.currency \?\? ""\) : inst \? inst\.currency \|\| \(inst\.market === "IN" \? "INR" : ""\) : "";/);
  // a re-run of an earlier set-up of today opens that run
  assert.match(nb, /Number\(\/\\bv\(\\d\+\)\\b\/\.exec\(e\.message\)/);
});

test("DP1-010: a row counts the trade still open beside the closed ones", () => {
  assert.equal(N.tradesCount(0, 1), "0 closed trades, 1 still open");
  assert.equal(N.tradesCount(5, 0), "5 trades");
  assert.equal(N.tradesCount(1, 2), "1 closed trade, 2 still open");
});

test("DP1-011: risk per trade with only a trailing stop says it is measured from the trail", () => {
  assert.match(read("src/components/Rules.tsx"), /if the \{r\.trail\}% trailing stop is hit, so each trade is sized to that/);
});

test("DP1-013, DP1-015: the start dialog says Free's trial and its last day in India's calendar, and that a stop is final", () => {
  assert.equal(P.trialLastDay("2026-10-29T18:30:00+00:00"), "Thu 29 Oct");          // midnight India time after the 29th
  assert.match(P.trialStartLine({ started: false, active: false, ends_at: null, days: 5 }), /^On Free, paper trading is a trial of 5 Indian market days from this first start \(weekends and market holidays don't count, even for crypto\)/);
  assert.equal(P.trialStartLine({ started: true, active: true, ends_at: "2026-10-29T18:30:00+00:00", days: 5 }),
    "Your Free trial runs until the end of Thu 29 Oct (India time); the session stops then unless you upgrade.");
  assert.equal(P.trialStartLine(null), null);
  assert.equal(P.trialStartLine({ started: true, active: false, ends_at: "2026-10-29T18:30:00+00:00" }), "Your Free paper trading trial has ended, so a new session needs Basic or Pro.");
  assert.match(P.STOP_IS_FINAL, /can't be restarted or paused/);
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /me\?\.plan === "free" && trialStartLine\(me\.trial\) \? <span className="k-note" data-testid="paper-trial">/);
  assert.match(read("src/pages/PaperPage.tsx"), /`Free trial until the end of \$\{trialLastDay\(me\.trial\.ends_at\)\} \(India time\)`/);
});

test("DP1-014, DP1-016: the session limit and a group's candles are said on the button, before any dialog", () => {
  assert.equal(P.liveLimitLine(1, 1, { name: "Basic", limit: 2 }), "Your plan runs 1 live strategy at a time and one is running. Stop one first, or Basic runs 2.");
  assert.equal(P.liveLimitLine(2, 2, { name: "Pro", limit: 10 }), "Your plan runs 2 live strategies at a time and 2 are running. Stop one first, or Pro runs 10.");
  assert.equal(P.liveLimitLine(0, 1, null), null);
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /if \(liveFull\) \{ plansToast\(liveFull\); return; \}/);
  assert.match(nb, /const groupDaily = !!group && groupOk && s\.tf === "1d";/);
  assert.ok(plans.FLAGS.some(([f, l]) => f === "group_live" && /5-minute, 15-minute or 1-hour candles/.test(l)));
});

test("DP1-017: the market page says a running session keeps its old pick", () => {
  assert.match(read("src/pages/MarketPage.tsx"), /A new pick here changes what the notebook tests, not the session: it keeps trading/);
});

test("DP1-019: locked pages show what they hold, and ask the server nothing it would refuse", async () => {
  for (const f of ["src/pages/BizUpdatesPage.tsx", "src/pages/HoldersPage.tsx", "src/pages/trade/ReplayPage.tsx", "src/pages/trade/SignalsPage.tsx"]) {
    assert.match(read(f), /<LockedPreview title="/, f);
  }
  assert.match(read("src/pages/BizUpdatesPage.tsx"), /const off = me\?\.plan_info\.features\?\.biz_updates === false;/);
  assert.match(read("src/pages/HoldersPage.tsx"), /const off = me\?\.plan_info\.features\?\.holders === false;/);
  // and the menu marks them locked on a plan without them
  const { gateFor } = await import("../src/lib/gates.ts");
  assert.equal(gateFor("/invest/business-updates").whole, true);
  assert.equal(gateFor("/invest/holders").whole, true);
});

test("DP1-020: home tiles for a paid tool say its plan on the tile", () => {
  const ex = read("src/components/Explore.tsx");
  assert.match(ex, /lockedOn\(f\.flag\) \? `On the \$\{lockedOn\(f\.flag\)\} plan →`/);
  const feats = read("src/lib/features.ts");
  for (const f of ["scans", "filings", "alerts", "investor_home"]) assert.match(feats, new RegExp(`flag: "${f}" \\}`), f);
  assert.match(read("src/pages/SpaceHomes.tsx"), /title: "Trend scan", line: "Stocks in a rising trend with the Supertrend up\.", flag: "scans" \}/);
});

test("DP1-021, DP1-022, DI-032, DP1-026: an honest Free line, decks one per company, and the comparison in parts", () => {
  assert.equal(plans.WHO.free, "Every market and the core tools, free");
  assert.ok(plans.FEATURES.free.some((l) => /each with the report card and checklist/.test(l) && /its PDF and PowerPoint count as one/.test(l)));
  // every paid feature row belongs to one of the three parts
  const groups = new Set(plans.FLAG_GROUPS.map((g) => g.id));
  for (const [f] of plans.FLAGS) assert.ok(groups.has(plans.FLAG_GROUP[f] ?? "research"), f);
  assert.ok(plans.FLAGS.filter(([f]) => plans.FLAG_GROUP[f] === "trade").length >= 10);
  const cmp = read("src/components/PlanCompare.tsx");
  assert.match(cmp, /<Disclosure summary=\{`On every plan \(\$\{everyone\.length\} tools\)`\}>/);
  assert.match(cmp, /import \{ Disclosure \} from "\.\/kit\/Disclosure";/);           // the landing page's small bundle
  assert.equal(deepDiveLimitLine(1, 2, 1, 1), "Companies opened this month: 1 of 2. Decks: 1 of 1 (limit reached); a company's PDF and PowerPoint are one deck. Opening a company again this month doesn't count.");
});

test("DP1-025: the options page says pricing needs the live quotes when they're offline, with one info icon", () => {
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /Pricing a structure works on every plan\{offline && !recordedUnd \? ", once the live option quotes are back" : ""\}\./);
  assert.doesNotMatch(src, /<Info label="About options backtesting">/);
});

test("DP1-028: the welcome question asked on a space's home says where you are", () => {
  assert.match(read("src/components/LevelPrompt.tsx"), /`You're on \$\{SPACES\[here\]\.label\} now: pick \$\{SPACES\[here\]\.label\} to stay, or another to open its home\.`/);
});
