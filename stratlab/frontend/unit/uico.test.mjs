// UI-CO (29 Oct 2026): the owner's company-page, Compare and Screener fixes: tables with headers and aligned columns instead of loose lines.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("item 7: the management report card is a table (Target | For | Said | Result) with the quote under the target, and says why it can't check", () => {
  const dd = read("src/pages/DeepDive.tsx");
  assert.match(dd, /<DataTable label="Management targets and how they turned out" stack/);
  for (const h of ['header: "Target"', 'header: "For"', 'header: "Said"', 'header: "Result"']) assert.ok(dd.includes(h), h);
  assert.match(dd, /<span className="k-note rc-quote">"\{r\.quote\}"<\/span>/);       // the quote sits under the target's name
  assert.match(dd, /data-testid="rc-why"/);                                           // one short line on why it can't be checked
  assert.doesNotMatch(dd, /className="promise-facts k-note">\s*\{r\.period/);          // the loose "For / Target / Actual" run of words is gone
  // a multiple is printed as one ("3–4×"), a percentage as said; a net margin has its own name
  assert.match(dd, /unit === "x" \? "×"/);
  assert.match(dd, /net_margin: "Net margin"/);
  assert.match(dd, /gross_margin: "Gross margin"/);
  // a plan with no figure is not "couldn't check": it has its own line under the counts
  assert.match(dd, /more \{c\.no_figure === 1 \? "is a plan" : "are plans"\} with no figure to check/);
});

test("item 1: corporate actions are one table with headers; the dividend total stays a line above it and long notes are numbered notes", () => {
  const c = read("src/components/CorpActions.tsx");
  for (const h of ['header: "Ex-date"', 'header: "Type"', 'header: "Amount a share"', 'header: "Record date"']) assert.ok(c.includes(h), h);
  assert.match(c, /Dividends with an ex-date in the last 12 months/);
  assert.ok(c.indexOf("Dividends with an ex-date in the last 12 months") < c.indexOf("<DataTable"));          // the summary line is above the table
  assert.match(c, /head: "Coming up"/);                                                                      // nothing ahead: a line in the table's own style
  assert.match(c, /<ul className="k-note cmp-foots" data-testid="div-now">/);                                // "in today's shares": a numbered note
  assert.doesNotMatch(c, /inv-rows/);                                                                        // no more two columns of chips
});

test("item 2: Key numbers are small tables (name | Value | Basis | Range), one width, no long qualifier inside a row", () => {
  const r = read("src/components/Research.tsx");
  for (const h of ['header: "Value"', 'header: "Basis"', 'header: anyBar ? <span title="Where this figure sits on a typical range for that measure">Range</span> : ""']) assert.ok(r.includes(h), h);
  assert.match(r, /if \(m\.note && m\.note\.length > LONG_NOTE\) foot\.push/);                                  // a long qualifier is a numbered note under the tables
  assert.match(r, /\{mark\(m\) && <sup className="cmp-foot-mark"/);                                               // marked next to the value
  assert.match(r, /m\.note && !mark\(m\) \? m\.note : ""/);                                                      // and never inside the row
  const css = read("src/styles-invest.css");
  assert.match(css, /\.inv-mt \.k-table \{ table-layout: fixed; \}/);
  assert.doesNotMatch(css, /\.inv-metric \{ display: grid/);
});

test("item 3: the AI read's numbers are one table (area | figures) with the valuation, the notable figures, where it sits and what to watch in it", () => {
  const r = read("src/components/Research.tsx");
  assert.match(r, /<DataTable label="The AI read, by area"/);
  for (const a of ['area: "Valuation"', 'area: "Notable figures"', 'area: "Where it sits"', 'area: "What to watch"']) assert.ok(r.includes(a), a);
  assert.match(r, /<dl className="ai-figs">/);
  assert.doesNotMatch(r, /className="inv-two"/);                                                                  // no more half-empty two-column blocks
  assert.match(r, /data-testid="notable-figures"/);
});

test("item 4: the price header is one block: price and change, market value, the 52-week bar, then badges, then the buttons", () => {
  const p = read("src/pages/Research.tsx");
  const i = (t) => { const k = p.indexOf(t); assert.ok(k > 0, t); return k; };
  assert.ok(i('className="k-stack inv-head-quote"') < i('className="k-stack inv-head-cap"'));
  assert.ok(i('className="k-stack inv-head-cap"') < i('className="k-stack inv-head-price"'));
  assert.ok(i('className="k-stack inv-head-price"') < i('className="k-stack inv-head-more"'));
  assert.ok(i('className="k-stack inv-head-more"') < i('className="k-row inv-actions"'));
  const css = read("src/styles-invest.css");
  assert.match(css, /@media \(max-width: 560px\) \{ \.inv-head \{ grid-template-columns: minmax\(0, 1fr\); \} \}/);
});

test("item 5: the investor checklist is a table a group (Check with its rule under it | Value | Result), one under the other", () => {
  const dd = read("src/pages/DeepDive.tsx");
  assert.match(dd, /<DataTable label=\{`Investor checklist: \$\{g\}`\}/);
  assert.match(dd, /header: "Value", numeric: true/);
  assert.match(dd, /header: "Result"/);
  assert.match(dd, /<span className="k-note">\{x\.rule\}<\/span>/);                                  // the rule is small text under the check's name
  const css = read("src/styles.css");
  assert.match(css, /\.checklist \{ display: flex; flex-direction: column; gap: var\(--s5\); \}/);        // no more two-column masonry
  assert.doesNotMatch(css, /\.checklist \{ columns: 2/);
});

test("item 6: the documents read, the business model, the measures, the plans and the documents are tables", () => {
  const dd = read("src/pages/DeepDive.tsx");
  assert.match(dd, /function DocTable\(/);
  assert.match(dd, /<DocTable label="The documents the read used"/);                                  // not one long run-on line
  assert.match(dd, /<DocTable label="Documents" docs=\{v\.documents\}/);
  assert.match(dd, /header: "Share of revenue"/);
  assert.match(dd, /label="The business, in the company's words"/);                                  // customers, drivers, strengths and risks on one grid
  assert.match(dd, /label="Capex plans, in management's words"/);
  assert.match(dd, /label="Outlook, in management's words"/);
  assert.match(dd, /label="Operating measures, from the company"/);
  assert.doesNotMatch(dd, /className="rs-grid"/);
  assert.doesNotMatch(dd, /className="promises"/);
  assert.match(dd, /<DataTable label="Growth a year"/);                                              // the growth tiles are a table too
  assert.match(dd, /<DataTable label="How it's valued"/);
});

test("item 8 (LIVE1A-048): a long note on a compared figure is a numbered note under its table, with its mark beside the value", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /note\.length > 48/);
  assert.match(r, /<sup className="cmp-foot-mark" aria-label=\{`see note \$\{foot\.n\}`\}>/);
  assert.match(r, /data-testid="cmp-note"/);
});

test("item 11: Compare shows its two companies as one table; a link with no market tries the other market once", () => {
  const r = read("src/pages/Research.tsx");
  assert.match(r, /<DataTable label="The two companies"/);
  assert.ok(r.indexOf('label="The two companies"') < r.indexOf('title="The numbers side by side"'));
  assert.ok(r.indexOf('title="The numbers side by side"') < r.indexOf('<CardHead title="AI comparison" />'));       // the figures first, the AI paragraph after (LIVE1A-049)
  assert.match(r, /if \(!params\.get\("region"\) && !t\.tried\)/);                                              // LIVE2-021
});

test("item 9: the Screener's numeric filters are a table; one Filters (n) bar on a phone; results before Save", () => {
  const s = read("src/pages/Screens.tsx");
  assert.match(s, /<DataTable label="Filters on figures: at least and at most"/);
  assert.match(s, /className="k-input-unit"/);                                                              // the unit inside the box, whatever it is
  assert.match(s, /title=\{n \? `Filters \(\$\{n\}\)` : "Filters"\}/);
  assert.match(s, /className=\{`screens-save\$\{showFilters \? "" : " folded"\}`\}/);
  const css = read("src/styles.css");
  assert.match(css, /\.screens-main > \.screens-save\.folded \{ display: none; \}/);
});

test("item 12 (LIVE2-020): the Screener's filters that can't load say so with a Try again", () => {
  const s = read("src/pages/Screens.tsx");
  assert.match(s, /<ErrorState title="The filters couldn't be loaded" action=\{\{ label: "Try again", onClick: \(\) => setMetaTries/);
  assert.match(s, /\}, \[region, metaTries\]\);/);
});

test("item 10, 13 (LIVE2-032, LIVE2-030): the tables fit a phone's card (no sideways scroll); the chart's (i) is 44px", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.dd-fit \.k-table :is\(th, td\) \{ white-space: normal; min-width: 0 !important;/);
  assert.match(read("src/components/Research.tsx"), /<div className="dd-fit"><DataTable label="Who owns it"/);
  assert.match(read("src/pages/DeepDive.tsx"), /<div className="dd-fit"><DataTable label=\{label\} rows=\{docs\}/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-info\.info-btn \{ width: 44px; height: 44px; \}/);
});

test("item 14: Trend scan has Build your own: the notebook's rule sentences, the notebook's words builder, a check under the box, a limit on rules and groups", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /const CUSTOM_SCAN: ScanInfo = \{ id: CUSTOM_ID, name: "Build your own"/);
  assert.match(s, /<ConditionList conds=\{conds\}/);
  assert.match(s, /import \{ buildIdea \} from "\.\.\/components\/IdeaComposer"/);                           // the existing parser of words into rules
  assert.match(s, /data-testid="custom-error"/);
  assert.match(s, /ready-made scans only/);
  assert.match(s, /body: \{ region, set: setId, scan: scan\.id, \.\.\.\(custom \? \{ rules: conds, within \} : \{\}\) \}/);
  const rules = read("src/components/Rules.tsx");
  assert.match(rules, /export function ConditionList\(/);
  assert.match(rules, /<CondSentence key=\{i\}/);                                                           // the very sentence the notebook edits
  assert.match(rules, /tf="1d"/);
});

test("tables everywhere on the company page: where a sale goes, who owns it, what they do and similar companies are tables", () => {
  const c = read("src/components/Research.tsx");
  assert.match(c, /<DataTable label="Where a sale goes"/);
  assert.match(c, /<DataTable label="Who owns it"/);
  assert.match(c, /export function QuoteTable\(/);
  const r = read("src/pages/Research.tsx");
  assert.match(r, /<DataTable label="Facts about the company"/);
  assert.match(r, /<QuoteTable region=\{region\} symbols=\{c\.peers\}/);
  assert.doesNotMatch(r, /className="k-dl pairs"/);
});

test("Screener results fit beside the filters (the sector wraps); the account banner's Retry steps aside for a page's own Try again", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.screens-table td \{ white-space: normal; \}/);
  assert.match(css, /body:has\(main \.k-state\.error button, main \.k-state\.error a\.btn\) \.banner \.account-retry \{ display: none; \}/);
  assert.match(read("src/components/AccountWait.tsx"), /className="btn sm quiet account-retry"/);
});
