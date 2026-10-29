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
