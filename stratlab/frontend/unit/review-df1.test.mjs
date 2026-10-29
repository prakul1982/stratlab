// The Invest data pages' audit (DF-001 to DF-023): ETF vs NAV, business updates, named holders, the margin funding
// calculator, stock lending and the Invest home — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const etf = (over = {}) => ({ symbol: "MONQ50", name: "Motilal Oswal Nasdaq Q50 ETF", underlying: null, fund: "intl", fund_label: "International ETF",
  price: 220.17, price_at: "2026-10-23T15:48+05:30", inav: null, inav_gap: null, nav: 118.3705, nav_date: "2026-10-23", nav_gap: 86.0, gap: 86.0,
  basis: "NAV", text: "MONQ50 trades 86.0% above its last NAV", ...over });

test("DF-001: a wide gap at the price shown is a gap, not dropped; a NAV of another unit still is", async () => {
  const { gapAtPrice, gapShort } = await import("../src/lib/etfGapMath.ts");
  const r = gapAtPrice(etf(), 220.17, "2026-10-23");                      // MONQ50's close against its NAV, 23 Oct 2026
  assert.equal(r.nav_gap, 86);
  assert.equal(gapShort(r.gap), "86.0% above");
  assert.equal(gapAtPrice(etf(), 400, "2026-10-23").gap, null);           // 3.4 times the NAV: another unit's NAV
  assert.equal(gapAtPrice(etf(), 30, "2026-10-23").gap, null);            // a quarter of it
  const page = read("src/pages/EtfGapsPage.tsx");
  assert.match(page, /beyond 50%: usually a fund not making new units/);
  assert.match(page, /left out: the price is 3 or more times the NAV/);
});

test("DF-003: the range says how many days it used, never a promised 30", async () => {
  const { dayCount } = await import("../src/lib/etfGapMath.ts");
  assert.equal(dayCount({ days: 14, stored: 14 }), "14 days");
  assert.equal(dayCount({ days: 13, stored: 14 }), "13 of 14 days");
  assert.equal(dayCount({ days: 1 }), "1 day");
  const page = read("src/pages/EtfGapsPage.tsx");
  assert.match(page, /header: "Up to 30 trading days"/);
  assert.doesNotMatch(page, /header: "30 trading days"/);
});

test("DF-005/006/007/008: the last trade's own day, a closed day's NAV, no iNAV said once, overseas NAVs explained", () => {
  const page = read("src/pages/EtfGapsPage.tsx");
  assert.match(page, /lastTradeDay\(r\)/);
  assert.match(page, /r\.price_day \? fmtDate\(r\.price_day/);
  assert.match(page, /a day with no trading/);
  assert.match(page, /An indicative NAV \(the fund house's estimate through the day\) isn't shown/);
  assert.match(page, /from overseas closes/);
  assert.match(page, /Each row shows two prices: the last trade, and the official close the gap uses/);
});

test("DF-014/015: business-update tables are cards on a phone, and an empty My stocks is one line with real links", () => {
  const page = read("src/pages/BizUpdatesPage.tsx");
  assert.match(page, /<DataTable stack label="My stocks' latest business updates"/);
  assert.match(page, /<DataTable stack label=\{d\.label\}/);
  assert.match(page, /k-swipe-hint/);
  assert.doesNotMatch(page, /star companies in Research/);                // there's no "Research" in the menu
  assert.match(page, /to="\/holdings">My Holdings<\/Link> or your <Link className="link" to="\/research\/watchlist">watchlist/);
  assert.doesNotMatch(page, /cement, airlines and airports, power, telecom/);   // nothing advertised that isn't filed (DF-013)
  assert.match(read("src/styles.css"), /@media \(max-width: 640px\) \{ \.k-swipe-hint \{ display: block; \} \}/);
});

test("DF-016/017/019: renamed holders said so, the Search button beside its box, following said plainly", () => {
  const page = read("src/pages/HoldersPage.tsx");
  assert.match(page, /filed under another name in \{hold\.renamed\}/);
  assert.match(page, /filed as \{r\.names\.join\(", "\)\}; last quarter as/);
  assert.match(page, /className="holder-search"/);
  assert.match(page, /Named in the most companies:/);
  assert.match(page, />Stop following<\/button>/);
  assert.doesNotMatch(page, />Following · stop</);
  assert.match(read("src/components/NamedHolders.tsx"), /filed last quarter as \{h\.was_named\}/);
  assert.match(read("src/styles.css"), /\.holder-search \{ display: flex;/);
});

test("DF-018: the US tab's heading says what it is, and a holder can be searched", () => {
  const page = read("src/pages/HoldersPage.tsx");
  assert.match(page, /title="US holders above 5%: S&P 500 companies"/);
  assert.match(page, /Look up a company, or a holder across companies/);
  assert.match(page, /\.\.\.\(holder \? \{ holder \} : \{\}\)/);
  assert.match(page, /Only filings whose cover page has been read can be found by holder/);
  assert.match(page, /newest filed \$\{fmtDate\(data\.newest\)\}/);
});

test("DF-020: the calculator checks each box against the server's limits, and an old answer never stays under new figures", async () => {
  const { costProblems, COST_LIMITS } = await import("../src/lib/mtfCost.ts");
  const ok = { buy: "1000", qty: "100", margin_pct: "25", rate_pct: "15", days: "30", charges: "", price: "", maint_pct: "" };
  assert.deepEqual(costProblems(ok), {});
  assert.equal(costProblems({ ...ok, margin_pct: "100" }).margin_pct, "Enter less than 100%.");
  assert.equal(costProblems({ ...ok, margin_pct: "0" }).margin_pct, "Enter more than 0%.");
  assert.equal(costProblems({ ...ok, qty: "0" }).qty, "Enter more than 0.");
  assert.equal(costProblems({ ...ok, buy: "0" }).buy, "Enter more than ₹0.");
  assert.equal(costProblems({ ...ok, days: "100000" }).days, "Enter at most 3,650.");
  assert.equal(costProblems({ ...ok, days: "2.5" }).days, "Enter a whole number.");
  assert.equal(costProblems({ ...ok, rate_pct: "61" }).rate_pct, "Enter at most 60% a year.");
  assert.equal(costProblems({ ...ok, maint_pct: "100" }).maint_pct, "Enter less than 100%.");
  assert.equal(COST_LIMITS.days.max, 3650);                                // mtf.CostReq: days le=3650
  const page = read("src/pages/MarginFundingPage.tsx");
  assert.match(page, /setOut\(null\);\s+\/\/ the old answer is for the old figures/);
  assert.match(page, /label=\{`Holding for \$\{days\} day/);
  assert.match(page, /const days = out\?\.for_days \?\? 0;/);
  assert.doesNotMatch(page, /fail\(err\)/);                               // no toast: the problem sits under its box
});

test("DF-021: a range is offered only well past its length, and the axis is in crore", async () => {
  const { rangesFor, axisCrore } = await import("../src/lib/mtfCost.ts");
  assert.deepEqual(rangesFor(44), []);                                     // 44 days: "All" only, no look-alike "1M"
  assert.deepEqual(rangesFor(50).map(([v]) => v), ["1m"]);
  assert.deepEqual(rangesFor(400).map(([v]) => v), ["1m", "3m"]);
  assert.equal(axisCrore(142500), "₹1,42,500 cr");
  assert.doesNotMatch(read("src/pages/MarginFundingPage.tsx"), /axisInr\(v \* CRORE\)/);
});

test("DF-022: lending across the market for anyone, and the lending facts as headings over prose", () => {
  const page = read("src/pages/StockLendingPage.tsx");
  assert.match(page, /Lending across the market on \$\{dayText\(m\.day\)\}/);
  assert.match(page, /\{ value: "fee", label: "Highest fee" \}/);
  assert.match(page, /<FactTable label="How the lending fee works" itemHead="Point" figureHead="What it says"/);          // (O7 tables: the facts are a table of points)
  assert.match(read("src/styles.css"), /\.k-dl\.prose dd \{ font-weight: 400;/);
});

test("DF-023: Invest home's first steps in one line, the next expiry in Coming up, no short card beside a tall one", () => {
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /<Top compact \/>/);
  assert.match(home, /e\.kind === "expiry"/);
  // VR1-010/011 replaced the two equal-height pairs: the watchlist beside Coming up and Results today stacked
  // (VR6-011: with nothing watched the three stack across the page instead; the pair stays as it was when there is a watchlist)
  assert.match(home, /<WatchPanel region=\{region\} \/>\s*\{fewWatched \? <><NextEvents region=\{region\} \/><ResultsToday region=\{region\} \/><\/> : \(\s*<div className="space-col">\s*<NextEvents region=\{region\} \/>\s*<ResultsToday region=\{region\} \/>/);
  assert.match(read("src/components/FirstSteps.tsx"), /if \(compact\) \{/);
  assert.match(read("src/styles.css"), /\.space-panels\.even \{ align-items: stretch; \}/);
});
