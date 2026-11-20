import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// site83 (Release 83): the centre alignment sweep (owner, 20 Nov), checked in the source; e2e/site83-align.spec.ts and ui-lint's R29 measure it.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Centre alignment (owner, 20 Nov): fold rows centred with the chevron a column of its own, the body the row's width, the column centred", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-fold-head, \.k-fold-sum \{ display: grid; grid-template-columns: var\(--fold-cols\) 10px; column-gap: var\(--s4\); align-items: center; padding-inline: var\(--s3\); \}/);
  assert.match(css, /details\.k-fold \{ display: block; \}/);
  assert.match(css, /\.k-fold-sum::after \{ content: ""; justify-self: end; align-self: center;/);
  assert.doesNotMatch(css, /\.k-fold-sum::after \{[^}]*top: 22px/);
  assert.match(css, /\.h-sum\.wide \.k-table td \{ vertical-align: middle; \}/);
  assert.match(read("src/components/kit/FoldTable.tsx"), /"minmax\(min-content, 1fr\)"/);
  const mw = read("src/components/watch/launcher.css");
  assert.match(mw, /body:not\(\.mw-docked\) \.shell > \.main \{ padding-inline: 76px; \}/);
  // the strict layout check measures it on every route (R29) and the browser spec on Mutual funds, Holdings, Net worth and the tax report
  assert.match(read("e2e/ui-lint-rules.ts"), /add\("R29", cell, `the cell's contents sit/);
  assert.match(read("e2e/site83-align.spec.ts"), /fold body: insets/);
});

test("No table wider than its box (owner, 20 Nov): Mutual funds' redemptions, the tax report's sales and the brief's short columns fit", () => {
  const mf = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(mf, /\{ key: "held", header: "Bought, sold", numeric: true, cell: \(r\) => <>\{dateOnly\(r\.bought\)\}<span className="k-sub-line">\{dateOnly\(r\.sold\)\}<\/span><\/> \}/);
  assert.doesNotMatch(mf.slice(mf.indexOf("function SchemeSales")), /\{ key: "rate", header: "Rate"/);     // the rate is under the term now
  const tax = read("src/pages/TaxReportPage.tsx");
  assert.match(tax, /\{salesMore\.on && <span className="k-sub-line">\{qtyText\(r\.qty\)\} \{r\.qty === 1 \? "share" : "shares"\}<\/span>\}/);
  const sales = tax.slice(tax.indexOf("const saleCols"), tax.indexOf("const lotCols"));
  assert.doesNotMatch(sales, /\{ key: "qty", header: "Qty"/);
  assert.doesNotMatch(sales, /\{ key: "rate", header: "Rate"/);
  assert.match(read("src/components/BriefTables.tsx"), /wrap: t\.align\[k\] === "l" && k > 0 && longest\(t\.rows, k\) > WRAP_FROM/);
  assert.match(read("e2e/ui-lint-rules.ts"), /add\("R29", w, `a table \$\{he\.scrollWidth\}px wide in its \$\{he\.clientWidth\}px box`\)/);
});
