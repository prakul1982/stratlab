// MO-3 (25 Oct 2026): three tax layouts the owner called "weird UI", the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("MO-3a: the tax inputs are a three-column form, its switches sized to their choices and as tall as the boxes", () => {
  assert.match(read("src/pages/TaxReportPage.tsx"), /<FormGrid trio onSubmit/);
  assert.match(read("src/components/kit/Form.tsx"), /k-form-trio/);
  assert.match(css, /\.k-form\.k-form-trio \{ grid-template-columns: repeat\(auto-fit, minmax\(min\(260px, 100%\), 1fr\)\); max-width: 1000px; \}/);
  assert.match(css, /\.k-form\.k-form-trio > \.k-field:has\(> \.k-seg button:nth-child\(3\)\) \{ grid-column: auto; \}/);
  // not stretched to the column, and "New (default)" is not squeezed into two lines by equal shares
  assert.match(css, /\.k-form > \.k-field > \.k-seg \{ width: max-content; max-width: 100%; min-height: var\(--ctl\); align-items: stretch;/);
  assert.doesNotMatch(css, /\.k-form > \.k-field > \.k-seg button \{ flex: 1 1 0;/);
  // (UI-FIX-1) a label never wraps in its button; the field takes two columns instead
  assert.match(css, /\.k-form > \.k-field > \.k-seg button \{ flex: 1 1 auto; min-width: max-content;[^}]*white-space: nowrap/);
  assert.match(css, /\.k-form > \.k-field:has\(> \.k-seg\) \{ grid-column: span 2; \}/);
  assert.match(css, /@media \(max-width: 640px\), \(pointer: coarse\) \{ \.k-form > \.k-field > \.k-seg \{ padding: 0;/);   // 44px buttons in a 44px track
  const src = read("src/pages/TaxReportPage.tsx");
  assert.match(src, /label: "New \(default\)"/);                         // the words are kept
  // other income and its salary part come one after the other, inside the same grid
  assert.ok(src.indexOf('label="Other income"') < src.indexOf('label="Of which salary"'));
});

test("MO-3b: the year's two figures fill the card, and the Tax tools link is not left after a dot", () => {
  assert.match(css, /\.k-card\.compact > \.k-stats \{ flex: 1 1 100%; \}/);
  const src = read("src/pages/TaxReportPage.tsx");
  // RC2B-004: the link sits inside the note's sentence (it was a block of its own under the figure)
  assert.match(src, /const toolsLink = <Link className="link" to=\{fyLink\("\/money\/tax-tools", y\.fy\) \+ "&tab=advance"\}>Tax tools<\/Link>;/);
  assert.doesNotMatch(src, /<span className="k-stat-link">/);
  assert.doesNotMatch(src, /"" \} · <Link className="link" to=\{fyLink\("\/money\/tax-tools"/);
});

test("MO-3c: the downloads share the width equally and the facts in words leave the grid of figures", () => {
  assert.match(css, /\.k-downloads \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(min\(240px, 100%\), 1fr\)\);/);
  assert.match(css, /\.k-downloads \.btn \{[^}]*white-space: normal; min-width: 0; \}/);
  assert.match(css, /\.k-dl\.facts \{ grid-template-columns: repeat\(auto-fit, minmax\(min\(260px, 100%\), 1fr\)\); \}/);
  const src = read("src/pages/money/ItrExportPage.tsx");
  assert.match(src, /const isFigure = /);
  assert.match(src, /<dl className="k-dl facts" aria-label="This year's return">/);
  assert.match(src, /\(v\?\.summary \?\? \[\]\)\.filter\(\(s\) => !isFigure\(s\.value\) && s\.label !== "Financial year"\)/);
  // LIVE1B-028: the figures are the two answers as tiles and the rest as a list, all taken from the lines that are figures
  assert.match(src, /const figs = \(v\?\.summary \?\? \[\]\)\.filter\(\(s\) => isFigure\(s\.value\)\);/);
  // TABLE-SWEEP: the two answers lead the one table of the year's figures
  assert.match(src, /rows=\{\[\.\.\.figs\.filter\(\(s\) => HEADLINE\.test\(s\.label\)\), \.\.\.figs\.filter\(\(s\) => !HEADLINE\.test\(s\.label\)\)\]/);
  assert.doesNotMatch(src, /k-stat-text/);
  // the same test as the page: money is a figure, the year, the return and the audit are words
  const isFigure = (value) => /^[−+-]?[₹$\d]/.test(value) && value.length < 18;
  assert.ok(isFigure("−₹1,000") && isFigure("₹4,000") && isFigure("12"));
  assert.ok(!isFigure("FY 2025-26 (assessment year 2026-27)") && !isFigure("ITR-3 (business income: intraday or F&O)"));
  assert.ok(!isFigure("Applies: report by 21 October 2026, return by 21 November 2026"));
});
