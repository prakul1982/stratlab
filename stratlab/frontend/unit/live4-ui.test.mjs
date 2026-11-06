// LIVE4 (final live review, 6 Nov 2026): the presentation fixes (lane r13-ui). Each test names its finding.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");
const invCss = read("src/styles-invest.css");

test("LIVE4-010: DataTable's compact phone rows: two short lines, brief figures at the right, columns left off, lone dashes dropped", () => {
  const t = read("src/components/kit/DataTable.tsx");
  assert.match(t, /brief\?: boolean;/);
  assert.match(t, /phone\?: false;/);
  assert.match(t, /compact\?: boolean;/);
  assert.match(t, /\$\{stack && compact \? " compact" : ""\}/);
  assert.match(t, /c\.brief && "k-brief", c\.phone === false && "k-phone-off"/);
  // a lone dash is "no figure": left off a compact phone row, but a cell still loading (no text of its own) is kept
  assert.match(t, /export const dashOnly = \(text: string\): boolean => \/\^\\s\*\[–—-\]\\s\*\$\/\.test\(text\);/);
  assert.match(t, /\(cardsNow && !!compact && !c\.rowHeader && dashOnly\(cellText\(v\)\)\)/);
  const dashOnly = (text) => /^\s*[–—-]\s*$/.test(text);
  assert.equal(dashOnly("–"), true);
  assert.equal(dashOnly(" - "), true);
  assert.equal(dashOnly(""), false);
  assert.equal(dashOnly("−1.2%"), false);
  // the CSS: a flex row with a zero-height break after the name and the brief figures; no card boxes
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table tr \{ display: flex; flex-wrap: wrap;/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table tr::before \{ content: ""; order: -1; flex-basis: 100%; height: 0; \}/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table th\[scope="row"\] \{ order: -3;/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table td\.k-brief \{ order: -2;/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table td\.k-phone-off \{ display: none; \}/);
  // the brief figures carry no label: their rule comes after the one that shows labels
  assert.ok(css.indexOf("td.k-brief::before { display: none; }") > css.indexOf(".k-tbl-wrap.stack.compact .k-table td[data-label]::before"));
});

test("LIVE4-010: a link in a table cell never shrinks under its own words (COROMANDEL ran under its F&O tag)", () => {
  assert.match(css, /\.k-table td a, \.k-table th a \{ min-width: 32px; flex-shrink: 0; \}/);
});

test("LIVE4-010: the results calendar is compact on a phone and its headers fit one line on a desktop", () => {
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /columns=\{columns\} stack compact phonePage=\{10\}/);
  assert.match(page, /key: "px", header: "Price", numeric: true, brief: true/);
  assert.match(page, /key: "day", header: "Day", numeric: true, brief: true/);
  for (const k of ["cap", "rev", "pat"]) assert.match(page, new RegExp(`key: "${k}", [^\\n]*phone: false`), k);
  assert.match(invCss, /\.inv-day \.k-table thead th \{ white-space: nowrap; \}/);
  assert.match(invCss, /\.k-tbl-wrap\.compact \.res-moves, \.k-tbl-wrap\.compact \.res-plain, \.k-tbl-wrap\.compact \.res-name \{ display: none; \}/);
  // the day's CSV button shares the day's heading line; on a phone it says "CSV"
  assert.match(invCss, /\.inv-day > \.k-eyebrow \+ \.k-tbl-tools \{ grid-column: 2;/);
  assert.match(read("src/components/kit/DataTable.tsx"), /<span className="k-csv-verb">Download <\/span>CSV/);
  assert.match(css, /@media \(max-width: 640px\) \{ \.k-csv-verb \{ display: none; \} \}/);
});
