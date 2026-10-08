// Round 5, the owner's review on the live site (8 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { quoteAt } from "../src/lib/format.ts";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const IST = "Asia/Kolkata";

test("each watchlist price carries the time it was traded, in the market's zone (R5O-003)", () => {
  const now = new Date("2026-10-08T09:31:00Z");                      // 15:01 IST
  assert.equal(quoteAt("2026-10-08T15:01:12+05:30", IST, now), "15:01 IST");
  assert.equal(quoteAt("2026-10-07T15:29:59+05:30", IST, now), "7 Oct, 15:29 IST");   // a stale quote reads as stale
  assert.equal(quoteAt("2026-10-08", IST, now), "8 Oct");              // a daily candle: its day only
  assert.equal(quoteAt(null, IST, now), "");
  // both tabs show it, from the same quotes
  assert.match(read("src/pages/Research.tsx"), /quoteAt\(q\.at, marketTz\(region\)\)/);
  assert.match(read("src/pages/InvestorHome.tsx"), /quoteAt\(r\.price_at, marketTz\(region\)\)/);
});

test("an ETF badge never sets today's price against yesterday's NAV (R5O-005)", async () => {
  const { gapAtPrice } = await import("../src/lib/etfGapMath.ts");
  // 8 Oct 14:25 IST, Nifty -1.7%: NIFTYBEES at 254.15 against the 7 Oct NAV of 257.80 read "1.4% below"
  const row = { symbol: "NIFTYBEES", name: "Nippon India ETF Nifty 50 BeES", underlying: null, fund: "equity", fund_label: "Equity ETF",
    price: 254.15, price_at: "2026-10-08T14:25+05:30", inav: null, inav_gap: null, nav: 257.8026, nav_date: "2026-10-07",
    nav_gap: -0.08, nav_price: 257.60, nav_price_day: "2026-10-07", gap: -0.08, basis: "NAV", text: "NIFTYBEES closed 0.08% below its NAV on 7 Oct" };
  const today = gapAtPrice(row, 254.15, "2026-10-08");
  assert.equal(today.gap, -0.08);                      // the 7 Oct close's gap stands, not -1.42
  assert.equal(gapAtPrice(row, 254.15).gap, -0.08);    // a price of unknown day is never set against the NAV either
  assert.equal(gapAtPrice(row, 257.0, "2026-10-07").gap, -0.31);   // a 7 Oct price is
  const badge = read("src/components/EtfGap.tsx");
  assert.match(badge, /close` : ""\)/);
  assert.match(read("src/pages/EtfGapsPage.tsx"), /header: "Close vs NAV"/);
});

test("AAPL's page: no unsourced segment split, an insider net that matches its rows, US grouping (R5O-007)", async () => {
  const { signed, grouped } = await import("../src/lib/format.ts");
  assert.equal(signed(208772, 0, "US"), "+208,772");
  assert.equal(signed(-139005, 0, "US"), "−139,005");
  assert.equal(signed(-139005), "−1,39,005");                 // India keeps its grouping
  assert.equal(grouped(4753636, 0, "US"), "4,753,636");
  assert.equal(grouped(4753636), "47,53,636");
  const research = read("src/pages/Research.tsx");
  assert.match(research, /signed\(Math\.round\(v\), 0, region\)/);
  assert.match(research, /shares over the \{c\.insider\.rows\.length\} filing/);
  assert.doesNotMatch(research + read("src/components/Research.tsx"), /Revenue by segment|<Donut/);
});

test("TCS's key numbers: no scraped strengths and concerns, and a figure's note shows (R5O-011)", () => {
  const research = read("src/pages/Research.tsx");
  assert.doesNotMatch(research, /Strengths and concerns|c\.pros|c\.cons/);
  assert.match(read("src/components/Research.tsx"), /\{m\.label\}\{m\.note && <span className="k-sub-line">\{m\.note\}<\/span>\}/);
});

test("the screener starts with the largest companies (R5O-012)", () => {
  const screens = read("src/pages/Screens.tsx");
  assert.match(screens, /useState\("market_cap"\)/);
  assert.match(screens, /const \[desc, setDesc\] = useState\(true\)/);
  assert.doesNotMatch(screens, /the list is alphabetical/);
});

test("whole-number growth rates stay whole, and the compare page names each section (R5O-021)", async () => {
  const { metricText } = await import("../src/lib/researchFormat.ts");
  assert.equal(metricText({ label: "5Y", value: -12, unit: "%±", dp: 0 }, "INR"), "−12%");
  assert.equal(metricText({ label: "10Y", value: 6, unit: "%±", dp: 0 }, "INR"), "+6%");
  assert.equal(metricText({ label: "1Y", value: -31.42, unit: "%±" }, "INR"), "−31.4%");
  const research = read("src/pages/Research.tsx");
  assert.match(research, /label=\{`\$\{sec\.title\} for both companies`\}/);
  assert.match(research, /<span className="k-eyebrow">\{sec\.title\}<\/span>/);
});

test("the Money card's tax is the tax report's total, with the audit fact (R5O-022)", () => {
  const card = read("src/pages/SpaceHomes.tsx");
  assert.match(card, /year\?\.total\?\.available \? year\.total\.total/);
  assert.match(card, /Total tax estimate, \$\{year\?\.label/);
  assert.match(card, /\{year\?\.audit && <p className="small">\{year\.audit\}<\/p>\}/);
  assert.doesNotMatch(card, /Capital gains tax, \$\{year/);
});

test("dates: quarter ends, the app's date format for an expiry, ticks on trading days (R5O-026)", async () => {
  const { isQuarterEnd } = await import("../src/components/NamedHolders.tsx").catch(() => ({}));
  const named = read("src/components/NamedHolders.tsx");
  assert.match(named, /\["03-31", "06-30", "09-30", "12-31"\]\.includes\(iso\.slice\(5, 10\)\)/);
  assert.match(named, /isQuarterEnd\(v\.quarter\) \? "Quarter to" : "As of"/);
  if (isQuarterEnd) { assert.equal(isQuarterEnd("2026-09-30"), true); assert.equal(isQuarterEnd("2026-10-05"), false); }
  assert.match(read("src/pages/OptionsSession.tsx"), /expiry \$\{fmtDate\(snap\.expiry, \{ weekday: true \}\)\}/);
  const { tickOnPoint } = await import("../src/lib/chartFormat.ts");
  const ms = (d) => Date.parse(`${d}T00:00:00+05:30`);
  const IST = "Asia/Kolkata";
  // 2 Oct 2026 (Gandhi Jayanti) and 3 Oct (Saturday) have no point: their ticks land on Monday 5 Oct's and say so
  assert.equal(tickOnPoint({ t: ms("2026-10-02"), label: "2 Oct" }, ms("2026-10-05"), false, IST), "5 Oct");
  assert.equal(tickOnPoint({ t: ms("2026-10-03"), label: "3 Oct" }, ms("2026-10-05"), false, IST), "5 Oct");
  assert.equal(tickOnPoint({ t: ms("2026-10-07"), label: "7 Oct" }, ms("2026-10-07"), false, IST), "7 Oct");
  assert.equal(tickOnPoint({ t: ms("2026-10-01"), label: "Oct" }, ms("2026-10-01"), false, IST), "Oct");
});

test("rupees in Indian grouping, dollars in international, whatever the reader's locale (R5O-034)", async () => {
  const { bigMoney, money } = await import("../src/lib/format.ts");
  assert.equal(money(4753636, "INR"), "₹47,53,636");                 // an admin paper account, was 4,753,636
  assert.equal(money(10000, "USD"), "$10,000");
  assert.match(read("src/lib/format.ts"), /Math\.round\(v\)\.toLocaleString\("en-US"\)/);
  assert.equal(bigMoney(999_000, "USD"), "$999,000");
  assert.match(read("src/pages/admin/UsersSection.tsx"), /money\(s\.equity, s\.currency \?\? "INR"\)/);
});

test("holdings name what is left out of the totals and of Today (R5O-004)", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /Not in these totals: \{t\.no_cost\.symbols\.join/);
  assert.match(page, /last change is left out of Today/);
  assert.match(page, /r\.session !== t\.session/);
  assert.match(page, /view\.us && view\.us\.count > 0/);
  // the Money home's holdings panel reads the same totals and says the same: what is left out, and the one dollar rate
  const money = read("src/pages/SpaceHomes.tsx");
  assert.match(money, /Not in these totals: \{h\.totals\.no_cost\.symbols\.join/);
  assert.match(money, /h\.totals\.count - \(h\.totals\.no_cost\?\.count \?\? 0\)/);
  assert.match(money, /at ₹\$\{h\.usd_inr\.toFixed\(2\)\} a dollar/);
});

// ---------- the reliability, AI and flows side ----------
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
  // the facts wording, with the server's own label for the entry when it has one (R6V-005: the card and the page agree)
  assert.match(lib, /<VerdictBadge v=\{e\.verdict\.verdict\} facts label=\{e\.verdict\.label\} \/>/);
  assert.doesNotMatch(lib, /<VerdictBadge v=\{e\.verdict\.verdict\} \/>/);
  assert.match(lib, /<HoldLine e=\{e\} \/>/);
  // the card pieces live in components/LibraryBits.tsx since the public library shares them; it says the same
  const bits = read("src/components/LibraryBits.tsx");
  assert.match(bits, /\{num\(gap, 1\)\} points \{h\.gap < 0 \? "behind" : "ahead"\}/);
  const pub = read("src/pages/PublicLibrary.tsx");
  assert.match(pub, /<VerdictBadge v=\{e\.verdict\.verdict\} facts label=\{e\.verdict\.label\} \/>/);
  assert.match(pub, /<HoldLine e=\{e\} \/>/);
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

test("ETF vs NAV on a phone: cards, a page of the widest gaps, then Show all; bigger targets (R5O-017)", () => {
  const p = read("src/pages/EtfGapsPage.tsx");
  assert.match(p, /const TOP = 50;/);
  assert.match(p, /rows=\{all \|\| q\.trim\(\) \? rows : rows\.slice\(0, TOP\)\} rowKey=\{\(r\) => r\.symbol\} stack/);
  assert.match(p, />Show all \{rows\.length\}<\/button>/);
  assert.match(read("src/styles.css"), /\.k-table td a, \.k-table th a, \.k-table td \.btn\.sm, \.k-table td button, \.k-cal-ev a, \.k-cal-evs button \{ min-height: 32px;/);
});

test("tour, replay and journal (R5O-029)", () => {
  assert.match(read("src/components/kit/Coachmark.tsx"), /if \(el\.closest\("\.sidebar"\) && r\.right \+ GAP \+ w <= vw - EDGE\)/);
  const rp = read("src/pages/trade/ReplayPage.tsx");
  assert.match(rp, /if \(e\.key !== "ArrowRight"/);
  assert.match(rp, /aria-keyshortcuts="ArrowRight"/);
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /<TimeInput id=\{id\} label="Entry time"/);
  assert.match(j, /<TimeInput id=\{id\} label="Exit time"/);
  for (const k of ["symbol", "qty", "entry_price", "exit_price"]) assert.match(j, new RegExp(`error=\\{bad\\.${k}\\}`));
});

test("accessibility: grid rows, chart buttons, unique table names, skip links (R5O-030)", () => {
  assert.match(read("src/components/Charts.tsx"), /role="row"/);
  const rot = read("src/components/Rotation.tsx");
  assert.match(rot, /role="button" aria-pressed=\{focus === r\.id\}/);
  assert.match(rot, /onKeyDown=\{\(e\) => \{ if \(e\.key === "Enter" \|\| e\.key === " "\)/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /announcement \$\{n \+ 1\} of/);
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, />Skip to the page's sections</);
  assert.match(shell, />Skip to the menu</);
});

test("polish: Help's title, candle colours, card heights, option tiles, the menu's scroll hint (R5O-032, 035-038, 040)", async () => {
  const { titleFor } = await import("../src/lib/title.ts");
  assert.equal(titleFor("/help"), "Help · StratLab");
  const pc = read("src/charts/price/priceChart.css");
  assert.equal((pc.match(/--pc-up: var\(--up\); --pc-down: var\(--down\);/g) || []).length, 3);
  assert.doesNotMatch(pc, /#1F4FB5|#B4500F/);
  assert.match(read("src/styles-invest.css"), /^\.k-cols \{[^}]*align-items: start; \}/m);
  assert.match(read("src/styles.css"), /\.mine-slot\[data-card="coming"\], \.mine-slot\[data-card="watch"\] \{ align-self: start; \}/);
  assert.match(read("src/styles.css"), /\.k-tiles \{ display: grid; grid-template-columns: repeat\(auto-fill, minmax\(max\(140px, calc\(\(100% - 30px\) \/ 4\)\), 1fr\)\)/);
  assert.match(read("src/components/Shell.tsx"), /className="side-more"/);
});

test("the theme map says a company without a checked ticker isn't listed, not 'private' (R5O-008)", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /\{co\.name\} \(not listed\)/);
  assert.doesNotMatch(r, /\(private\)/);
});
