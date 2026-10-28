// MF-1 (RC2B-047, 045, 046, 049): the Mutual funds page says each scheme once.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const page = read("src/pages/money/MutualFundsPage.tsx");
const costs = read("src/pages/money/FundCosts.tsx");
const behaviour = read("src/pages/money/FundBehaviour.tsx");
const fold = read("src/components/kit/FoldTable.tsx");
const css = read("src/styles.css");

test("RC2B-047: one list of schemes, no second, third or fourth table of them", () => {
  // the schemes are one fold list (held, and the ones no longer held under it); the old tables of them are gone
  assert.equal((page.match(/<FoldTable label="Schemes"/g) ?? []).length, 1);
  assert.match(page, /<FoldTable label="Schemes you no longer hold"/);
  assert.doesNotMatch(page, /<DataTable label="Schemes"/);
  assert.doesNotMatch(costs, /<DataTable label="Fund costs"/);
  assert.doesNotMatch(behaviour, /<DataTable label="Your return against each fund's"/);
  assert.doesNotMatch(behaviour, /<DataTable label="Redemptions after a fall"/);
  // the year's card keeps its totals and the rates table; the sales are under each scheme, not a table of every scheme again
  assert.match(page, /<DataTable label="Gains by rate"/);
  assert.equal((page.match(/<DataTable label=\{`Redemptions matched to purchases, \$\{name\}`\}/g) ?? []).length, 1);   // named after its scheme: open folds sit side by side (A11Y-2)
  assert.match(page, /function SchemeSales/);
  assert.match(page, /salesOf\.get\(s\.key\)/);
});

test("RC2B-047: the row carries value, gain, XIRR, TER and the gap to the fund; the rest is in its fold", () => {
  for (const k of ['key: "val"', 'key: "gain"', 'key: "xirr"', 'key: "ter"', 'key: "gap"']) assert.ok(page.includes(k), k);
  assert.match(page, /<CostCell q=\{costs\} id=\{s\.key\} \/>/);
  assert.match(page, /<GapCell q=\{habits\} id=\{s\.key\} \/>/);
  // the fold holds the holding, the costs, the return and SIPs, the sales and the 31 Jan 2018 NAV
  for (const c of ["<SchemeHolding", "<CostDetail", "<BehaviourDetail", "<SchemeSales", "<FmvRow"]) assert.ok(page.includes(c), c);
  // a scheme that needs something looked at opens on its own, with its problem said in the row
  assert.match(page, /openWhen=\{open\}/);
  for (const w of ["Some units have no known cost", "Redeemed more than the statement shows bought", "ELSS units redeemed inside the lock-in", "Needs its 31 Jan 2018 NAV"]) assert.ok(page.includes(w), w);
});

test("RC2B-047: every fact the page showed is still reachable", () => {
  // the units, NAV, invested, folio, 'taxed as', ELSS lock-in, the cost and redemption warnings
  for (const w of ["Folio", "Units", "NAV", "Invested", "Taxed as", "ELSS lock-in:", 'data-testid="mf-short"', 'data-testid="mf-elss-early"']) assert.ok(page.includes(w), w);
  // costs: plan, TER and its date, both plans, the gap a year, since you bought, category changes, the parts of the TER
  for (const w of ["Direct plan TER", "Regular plan TER", "Gap a year", "TER since you bought", "Category changed on", "Parts of the TER", "Not in the TER disclosure yet"]) assert.ok(costs.includes(w), w);
  // behaviour: the period, gap in rupees, IDCW and short-span notes, the SIP record, the redemptions after a fall
  for (const w of ["Compared over", "Gap in ₹", "IDCW option", "Under a year", "SIP record.", "Redemptions after a fall of", "those units today"]) assert.ok(behaviour.includes(w), w);
  // the totals are one block: stats once, the explanations behind one fold
  assert.match(page, /<CostStats q=\{costs\} \/><BehaviourStats q=\{habits\} \/>/);
  assert.match(page, /summary="How this is worked out"/);
  // the by-category mix sits in the card of the totals (it was a card of its own)
  assert.doesNotMatch(page, /<CardHead title="By category"/);
  assert.match(page, /label="Funds by category"/);
});

test("RC2B-047: plan gates are as they were", () => {
  assert.match(page, /!view\.gains_allowed && <PlanNote>/);
  assert.match(page, /view\.limit != null &&/);
  assert.match(costs, /!c\.full && <PlanNote>/);
  assert.match(costs, /c\.full && s\.cost_year != null/);
  assert.match(behaviour, /!b\.full && <PlanNote>/);
  assert.match(behaviour, /!b\.full/);
  // no advice wording, no data-vendor names
  for (const src of [page, costs, behaviour]) {
    assert.doesNotMatch(src, /\b(you should|we suggest|recommend|better fund|switch to)\b/i);
    assert.doesNotMatch(src, /yahoo|finnhub|screener|kite/i);
  }
});

test("RC2B-047: the fold list is a kit piece; a phone row is a card with 44 px to tap", () => {
  assert.match(read("src/components/kit/index.ts"), /export \{ FoldTable \} from "\.\/FoldTable"/);
  assert.match(fold, /<details className="k-fold"/);
  assert.match(fold, /<summary className="k-fold-sum">/);
  assert.match(css, /\.k-fold-sum \{[^}]*min-height: 44px/);
  assert.match(css, /@media \(max-width: 720px\) \{\s*\.k-fold-head \{ display: none; \}/);
  // a scheme's facts are never 4 + 1 (UI checker R9)
  assert.match(css, /\.k-fold-body \.k-dl \{ grid-template-columns: repeat\(5, minmax\(0, 1fr\)\); \}/);
  // its detail is drawn only once opened
  assert.match(fold, /\{shown && <div className="k-fold-body">/);
});

test("RC2B-045: one US stock's value is its row's, not said again above the table", () => {
  const h = read("src/pages/HoldingsPage.tsx");
  assert.match(h, /view\.us\.count > 1 && <>: \{usd\(view\.us\.value\)\}/);
  // the line keeps what the table does not say: whether it is in the rupee totals, and where sales come from
  assert.match(h, /in the rupee totals above at/);
  assert.match(h, /Sales of US stocks come from the trades/);
});

test("RC2B-046: Tax tools' dividend card says the Indian total only when there is a US one beside it", () => {
  const t = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(t, /\{y\.us && <Stat label="Indian companies"/);
  assert.match(t, /!y\.us \? \(y\.tds\.threshold != null/);
  assert.equal((t.match(/<CardHead title="Your dividends"/g) ?? []).length, 1);          // only when there is no year to show
});

test("RC2B-049: a dividend on a phone Holdings page is a line in its card, not a card in a card", () => {
  assert.match(css, /#holdings-dividends \.k-tbl-wrap\.stack \.k-table tr \{ border: 0; border-bottom: 1px solid var\(--line\)/);
});
