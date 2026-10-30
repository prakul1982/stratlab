// FIX-1A: the findings of the live-site review LIVE-1A (trade and invest, 28 Oct 2026). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE1A-048/049: the compare page's qualifier is one numbered note under its table, and the AI read comes after the figures", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /<sup className="cmp-foot-mark"/);
  assert.match(r, /className="k-note cmp-foots" data-testid="cmp-note"/);
  // the AI card is drawn after "The numbers side by side"
  assert.ok(r.indexOf('<CardHead title="AI comparison" />') > r.indexOf('<CardHead title="The numbers side by side" />'));
  assert.match(read("src/charts/price/PriceChart.tsx"), /data-testid="pc-cmp-since"/);
  assert.match(read("src/styles.css"), /\.cmp-foots \{[^}]*overflow-wrap: anywhere/);
});

test("LIVE1A-051/006: a gap in points is readable, and a run of too few trades leads with that verdict", async () => {
  const { readablePoints, verdictLines } = await import("../src/lib/tradeUi.ts");
  assert.equal(readablePoints("11438.7 points behind buy and hold after costs."), "11,439 points behind buy and hold after costs.");
  assert.equal(readablePoints("3.8 points ahead of buy and hold after costs."), "3.8 points ahead of buy and hold after costs.");
  assert.equal(readablePoints("62.5 points behind."), "62.5 points behind.");
  const few = verdictLines("3.8 points ahead of buy and hold after costs; only 9 trades: too few to judge.", "not_enough");
  assert.deepEqual(few, { main: "Only 9 trades: too few to judge.", checks: "3.8 points ahead of buy and hold after costs.", swapped: true });
  const lost = verdictLines("Within a point of buy and hold after costs; lost money after costs.", "no_edge");
  assert.equal(lost.main, "Lost money after costs.");
  // a run that made money keeps the comparison first
  const ok = verdictLines("44.5 points ahead of buy and hold after costs; 4 of 4 checks run · 2 passed.", "mixed");
  assert.deepEqual(ok, { main: "44.5 points ahead of buy and hold after costs.", checks: "4 of 4 checks run · 2 passed.", swapped: false });
  assert.match(read("src/styles.css"), /\.verdict-head \{[^}]*line-height: 1\.05/);
});

test("LIVE1A-060/061: a US session still going on is not a close, and the banner names no company or error code", async () => {
  const { problemNote } = await import("../src/lib/ipoText.ts");
  const t = problemNote(["SEC filings for Amaero Inc.: The SEC is having trouble (500)."], "28 Oct, 12:00");
  assert.doesNotMatch(t, /Amaero|500|trouble/);
  assert.match(t, /filings couldn't be read/);
  assert.match(problemNote(["12 Sep calendar: timeout"], null), /a source couldn't be read/);
  assert.match(read("src/pages/IposPage.tsx"), /problemNote\(d\.problems/);
});

test("LIVE1A-029/030/031: bids say when they were read, the issue size shows its two parts, and unpriced listings fold away", () => {
  const p = read("src/pages/IposPage.tsx");
  assert.match(p, /data-testid="ipo-sub-at"/);
  assert.match(p, /counting the bids placed on both exchanges/);
  assert.match(p, /data-testid="ipo-size-parts"/);
  assert.match(p, /testId="ipo-unpriced"/);
});

test("LIVE1A-005/007/008/036: the verdict page's numbers and costs are full-width cards, its header wraps whole, its menus fit and the next steps stack on a phone", () => {
  const e = read("src/pages/ExperimentPage.tsx"), t = read("src/pages/trade/trade.css"), s = read("src/styles.css");
  assert.match(e, /className="k-rows two" role="list" aria-label="Profit and costs"/);
  assert.match(t, /\.k-money\.k-money-even \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(e, /className="k-toolbar next-steps"/);
  assert.match(t, /\.next-steps \{ flex-direction: column; align-items: stretch; \}/);
  assert.match(e, /label: `Compare with v\$\{Math\.max\(\.\.\.prev\)\}`/);
  assert.match(s, /\.more-pop \{[^}]*width: max-content/);
  assert.match(e, /className="link back-link"/);
});

test("LIVE1A-001/052: on a desktop window the Lab notes tab is an edge handle in the page's margin", () => {
  const s = read("src/styles.css");
  const i = s.indexOf("@media (min-width: 1100px) {\n  .ln-btn");
  assert.ok(i > 0);
  assert.match(s.slice(i, i + 700), /\.ln-btn \{ position: fixed; right: 0;/);
});

test("LIVE1A-015/016/017/018/019: the options builder's summary, notes, charges and settings", () => {
  const o = read("src/pages/OptionsPage.tsx"), m = read("src/components/OptionModel.tsx"), s = read("src/styles.css");
  assert.match(o, /label=\{i === 0 \? "Lower breakeven" : "Upper breakeven"\}/);               // two breakevens are two tiles
  assert.match(o, /<Disclosure className="opt-explain" summary="How these figures are worked out">/);
  assert.match(m, /<Disclosure className="opt-explain" summary="How the Greeks are worked out">/);
  assert.match(o, /label="Charges as % of premium"/);
  assert.match(s, /\.opt-charge-lines table \{ width: 100%; max-width: none;/);
  assert.match(o, /<FormGrid label="More settings" quad>/);
  assert.match(s, /\.k-form\.k-form-quad \{ grid-template-columns: repeat\(4, minmax\(0, 1fr\)\); \}/);
  assert.match(o, /"Buy a move, a spread, or your own"/);
  assert.match(o, /See the plans/);
});

test("LIVE1A-004: the instrument search groups its results and keeps most option strikes behind a row", async () => {
  const { arrange, OPTION_ROWS } = await import("../src/lib/instrumentGroups.ts");
  const rows = [{ id: "s", type: "EQ" }, { id: "f", type: "FUT" }, ...Array.from({ length: 12 }, (_, i) => ({ id: `o${i}`, type: i % 2 ? "PE" : "CE" }))];
  const a = arrange(rows, false);
  assert.equal(a.rows.length, 2 + OPTION_ROWS);
  assert.equal(a.hidden, 12 - OPTION_ROWS);
  assert.equal(a.rows[0].id, "s");
  assert.equal(arrange(rows, true).rows.length, 14);
});

test("LIVE1A-004 (source): groups and the show-more row", () => {
  const src = read("src/components/InstrumentSearch.tsx");
  assert.match(src, /className="search-more" role="option"/);
  assert.match(read("src/lib/instrumentGroups.ts"), /heads\.set\(first\.id, GROUPS\[g\]\)/);
});

test("LIVE1A-021/023/024/025/026/027/028: events, positioning, forward test, library and Sharpe", async () => {
  const ev = read("src/pages/trade/EventsPage.tsx");
  assert.match(ev, /v\.sources\.filter\(\(x\) => x\.id !== "index"\)/);       // the index provider's failure is said over the index changes
  assert.match(ev, /function IndexChanges\(\{ rows, failed \}/);
  const pos = read("src/pages/PositioningPage.tsx");
  assert.ok(pos.indexOf('<Stat label="DII sold"') < pos.indexOf('<Source testId="cash-source">'));       // the figures, then where they come from
  const sig = read("src/pages/trade/SignalsPage.tsx");
  assert.match(sig, /<div className="k-field wide"><CheckField label="Allow short positions"/);
  assert.match(read("src/components/LibraryBits.tsx"), /data-testid="lib-dates"/);
  const { SHARPE_MIN_DAYS, runDays } = await import("../src/lib/tradeUi.ts");
  assert.equal(SHARPE_MIN_DAYS, 180);
  assert.ok(Math.round(runDays({ range: { from: "2026-08-28", to: "2026-10-28" }, days: 730 })) === 61);
});

test("LIVE1A-032/034/035/039/041/043: scans, rotation, screens, red flags, alert kinds, plan before fetching", () => {
  const sc = read("src/pages/ResearchScans.tsx");
  assert.doesNotMatch(sc, /Deep dive →<\/Link><\/>\) \},\s*\n\s*\{ key: "p", header: "Price"/);
  assert.match(sc, /data-testid="rot-default-note"/);
  assert.match(sc, /data-testid="filings-not-refreshed"/);
  assert.match(read("src/pages/Screens.tsx"), /className="screens-filters-wait"/);
  assert.match(read("src/components/kit/Form.tsx"), /<optgroup key=/);
  assert.match(read("src/components/AlertForm.tsx"), /group: CONDITION_GROUP\[x\.kind\]/);
  assert.match(read("src/pages/HoldersPage.tsx"), /if \(!me\) return;/);
  assert.match(read("src/pages/BizUpdatesPage.tsx"), /if \(off \|\| !me\) return;/);
});

test("LIVE1A-048..050/062/063/064: company and compare pages", async () => {
  const r = read("src/pages/Research.tsx");
  assert.ok(r.indexOf('title="Key numbers"') < r.indexOf('<CardHead title="What they do"'));        // the figures before the description
  assert.match(r, /data-testid="trend-lakh"/);
  assert.match(r, /P\/E \$\{f\.pe\.toFixed\(2\)\}/);
  assert.match(read("src/components/Research.tsx"), /data-testid="metric-notes"/);
  const { tidyTitle } = await import("../src/lib/biz.ts");
  assert.equal(tidyTitle('Surrey announce their partnership in The Hundred."'), "Surrey announce their partnership in The Hundred.");
  assert.equal(tidyTitle("PLEASE FIND ATTACHED A MEDIA RELEASE ON RELIANCE'S JIO STUDIOS. IT BETS BIG"), "Please find attached a media release on reliance's jio studios. It bets big");
  assert.equal(tidyTitle("Monthly Business Update for September 2026"), "Monthly Business Update for September 2026");
});

test("LIVE1A-066: /plans carries its plans as structured data and as plain text", async () => {
  const { plansJsonLd, plansList } = await import("../scripts/seoPages.mjs");
  const ld = plansJsonLd();
  assert.match(ld, /"@type":"Product","name":"StratLab Basic"/);
  assert.match(ld, /"price":"699","priceCurrency":"INR"/);
  assert.match(ld, /"valueAddedTaxIncluded":true/);
  assert.match(plansList(), /₹1,999 a month or ₹19,999 a year, GST included/);
});

test("LIVE1A-003/010/056/057/058: the new-idea page and the builder's brokerage default", async () => {
  const h = read("src/pages/Home.tsx");
  assert.match(h, /hide=\{\[\.\.\.hide, "\/import", "\/library"\]\}/);          // IA-1: Explore hides pages by their address
  assert.doesNotMatch(h, /useEffect\(\(\) => \{ if \(where\.market\) try \{ localStorage\.setItem\(LAST_MARKET/);
  const { riskForCurrency, blankStrategy, noRuleNote } = await import("../src/lib/rules.ts");
  const r = blankStrategy().risk;
  assert.equal(riskForCurrency(r, "INR", { market: "IN", type: "EQ", tf: "1d" }).brokerage, 0);       // a delivery share starts at no brokerage
  assert.equal(riskForCurrency(r, "INR", { market: "IN", type: "FUT", tf: "1d" }).brokerage, 20);     // futures keep the flat ₹20 an order
  assert.equal(riskForCurrency(r, "INR", { market: "IN", type: "EQ", tf: "5m" }).brokerage, 20);      // intraday too
  assert.equal(riskForCurrency({ ...r, brokerage: 35 }, "INR", { market: "IN", type: "EQ", tf: "1d" }).brokerage, 35);   // a setting of the person's own stands
  assert.equal(riskForCurrency(r, "INR").brokerage, 20);
  assert.doesNotMatch(noRuleNote("asdf qwerty make me rich", ["No actionable strategy provided."]).note, /actionable/);
  assert.match(read("src/pages/MarketPage.tsx"), /Exports from charting sites, broker apps and Excel work as they are/);
});

test("LIVE1A-011/012/013/014/044/045/046/038: the paper pages", async () => {
  const { fillsLine } = await import("../src/lib/paperText.ts");
  assert.match(fillsLine({ slippage: 0.05, brokerage: 0 }, null, "₹0"), /The notebook's test fills at the next candle's open instead/);
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /<ul className="k-list paper-ask" data-testid="paper-ask">/);
  assert.match(read("src/pages/PaperPage.tsx"), /infoLabel="How orders fill and what they pay"/);
  const { qtyShort } = await import("../src/lib/format.ts");
  assert.equal(qtyShort(0.41205201), "0.4121");
  assert.equal(qtyShort(953.05257275), "953.0526");
  assert.equal(qtyShort(10), "10");
  assert.match(read("src/components/GroupSession.tsx"), /note=\{`Started with \$\{money\(a\.capital, cur, 0\)\}\. Fake money`\}/);
  assert.match(read("src/components/RiskOverview.tsx"), /The chart draws each day's close, so this low is not on it/);
});
