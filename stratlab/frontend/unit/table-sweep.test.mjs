// TABLE-SWEEP (owner, 29 Oct): on Net worth, Tax tools, Mutual funds, ITR export, the SIP test, US stocks tax and the Holdings
// totals, every block of figures or records is a table (headers, right-aligned numbers, a sign on every change), long qualifiers are
// numbered notes, nothing is cut short with "and N more" or "Show all", and no column stands half empty. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");
const PAGES = ["src/pages/money/NetWorthPage.tsx", "src/pages/money/TaxToolsPage.tsx", "src/pages/money/MutualFundsPage.tsx", "src/pages/money/ItrExportPage.tsx",
  "src/pages/money/SipTestPage.tsx", "src/pages/money/UsTaxPage.tsx", "src/pages/HoldingsPage.tsx", "src/pages/money/LoanCheck.tsx",
  "src/pages/money/FundCosts.tsx", "src/pages/money/FundBehaviour.tsx"];

test("TABLE-SWEEP: the swept pages have no tiles, bar lists, bullet lists or lists of label and value pairs left", () => {
  for (const p of PAGES) {
    const src = read(p);
    assert.doesNotMatch(src, /<Stat\b|<StatRow\b|<BarList\b/, `${p}: a tile or a bar list`);
    assert.doesNotMatch(src, /className="k-list/, `${p}: a bullet list (numbered notes or a table instead)`);
    assert.doesNotMatch(src, /<dl className="k-dl"(?! facts)/, `${p}: label and value pairs (a table instead)`);
  }
});

test("TABLE-SWEEP: nothing is cut short: no 'and N more', no 'Show all', no first-N slice of the rows", () => {
  for (const p of PAGES) {
    const src = read(p);
    assert.doesNotMatch(src, /Show all \{/, `${p}: a Show all button`);
    assert.doesNotMatch(src, /\band \$\{[^}]*\} more\b/, `${p}: "and N more"`);
    assert.doesNotMatch(src, /\.slice\(0, \d+\)\.(join|map)\(/, `${p}: a list cut to its first rows`);
    assert.doesNotMatch(src, /rows=\{[^}]*\.slice\(0, \d+\)/, `${p}: a table cut to its first rows`);
  }
});

test("TABLE-SWEEP: the kit's ShareTable replaces the bar list: name, count, detail, value and share, an empty column left out", () => {
  const src = read("src/components/kit/BarList.tsx");
  assert.doesNotMatch(src, /export function BarList/);
  assert.match(src, /export function ShareTable/);
  assert.match(src, /const has = \(k: "count" \| "detail" \| "value"\) => rows\.some\(\(r\) => r\[k\] != null && r\[k\] !== ""\);/);
  // on a phone it stays a table of three columns, the count and detail under the name
  assert.match(src, /has\("count"\) && !phone \?/);
  assert.match(src, /<div className="k-share"><DataTable [\s\S]*?stack=\{false\} \/><\/div>/);
  assert.match(css, /\.k-share \.dd-share \{ min-width: 56px; \}/);
  assert.match(read("src/components/kit/index.ts"), /Meter, ShareTable, type ShareRow/);
  assert.doesNotMatch(css, /\.k-bars\b/);
});

test("TABLE-SWEEP: long qualifiers are the kit's numbered Notes, an empty one left out", () => {
  const src = read("src/components/kit/Notes.tsx");
  assert.match(src, /const shown = items\.filter\(\(x\) => x != null && x !== false && x !== ""\);/);
  assert.match(src, /<ol className="k-notes" aria-label=\{label\}/);
  assert.match(css, /\.k-notes \{ margin: 0; padding-left: var\(--s5\);/);
  for (const p of ["src/pages/money/NetWorthPage.tsx", "src/pages/money/TaxToolsPage.tsx", "src/pages/money/MutualFundsPage.tsx", "src/pages/money/ItrExportPage.tsx",
    "src/pages/money/SipTestPage.tsx", "src/pages/money/UsTaxPage.tsx", "src/pages/money/LoanCheck.tsx"]) assert.match(read(p), /<Notes /, p);
});

test("TABLE-SWEEP: no half-empty column: a note column only when a row has a note, an empty phone cell left out", () => {
  const fig = read("src/components/kit/FigureTable.tsx");
  assert.match(fig, /const withNote = noteHeader != null && rows\.some\(noted\);/);
  assert.match(fig, /\.\.\.\(withNote && !under \? \[/);                       // on a phone the note sits under the name
  const fact = read("src/components/kit/FactTable.tsx");
  assert.match(fact, /\.\.\.\(notes && !under \? \[/);
  assert.match(fact, /const under = noteUnder && phone && notes;/);                 // the fund's fold asks for it; elsewhere a phone shows cards
  assert.match(read("src/pages/money/FundBehaviour.tsx"), /rows=\{facts\} noteUnder \/>/);
  assert.match(read("src/components/kit/DataTable.tsx"), /data-blank=\{blank \? "" : undefined\}/);
  assert.match(css, /\.k-tbl-wrap\.stack \.k-table td\[data-blank\] \{ display: none; \}/);
  const nw = read("src/pages/money/NetWorthPage.tsx");
  assert.match(nw, /\.\.\.\(view\?\.insurance\.policies\.some\(\(p\) => p\.next_due\) \? \[\{ key: "due", header: "Next due"/);   // no column of dashes
  assert.match(nw, /<FactTable label="Where you stand" itemHead="Total" figureHead="Now" noteHead="Change" numeric/);
  assert.match(read("src/pages/money/SipTestPage.tsx"), /\{ key: "name", header: "How the money went in", rowHeader: true/);
});

test("TABLE-SWEEP: the swept records: a loan's rate changes, a fund's falls, its costs, its holding, the lines an import left out", () => {
  const loan = read("src/pages/money/LoanCheck.tsx");
  assert.match(loan, /<DataTable label=\{`Rate changes on \$\{c\.name\}`\} columns=\{changeCols\} rows=\{\[\.\.\.c\.changes\]\.reverse\(\)\}/);
  assert.doesNotMatch(loan, /Earlier/);
  assert.equal((loan.match(/\{ key: "\w", header: /g) ?? []).length, 6);          // six columns: it fits its card at 1280
  const b = read("src/pages/money/FundBehaviour.tsx");
  assert.match(b, /<DataTable label=\{name \? `Redemptions after a fall, \$\{name\}`/);
  assert.match(b, /<FactTable label=\{name \? `How you invested in \$\{name\}`/);
  const c = read("src/pages/money/FundCosts.tsx");
  assert.match(c, /<FigureTable label=\{name \? `What \$\{name\} costs` : "What it costs"\}/);
  assert.match(c, /<Disclosure summary="Parts of the TER"><FigureTable label="Parts of the TER"/);
  const mf = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(mf, /<FigureTable label=\{`What you hold in \$\{s\.name\}`\}/);
  assert.match(mf, /<DataTable label="Lines left out" phonePage=\{10\} columns=\{problemCols\} rows=\{result\.problems\.map/);
  assert.match(mf, /rows=\{sales\.map\(\(r, i\) => \(\{ \.\.\.r, i \}\)\)\}/);
  // the holdings and the year's tax: figures as tables; a payable's total line in bold, TDS taken off with its sign
  assert.match(read("src/pages/HoldingsPage.tsx"), /<FigureTable label="Where your stocks stand" header="Total" valueHeader="Amount" noteHeader="Change"/);
  const tax = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(tax, /const total = i === p\.lines\.length - 1;/);
  assert.match(tax, /value: inr\(s\.tds > 0 \? -s\.tds : 0\)/);
  assert.match(read("src/pages/money/UsTaxPage.tsx"), /rows=\{v\.trades\}/);
});
