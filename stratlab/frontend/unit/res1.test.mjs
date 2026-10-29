// RES-1: the results calendar's table, its filters and what is read for the rows in view.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const page = read("src/pages/ResultsPage.tsx");

test("RES-1: one table a day with the figures a person looks at on a results day", () => {
  assert.match(page, /<DataTable label=\{`Results on \$\{resultDay\(d\)\}`\} rows=\{on\} rowKey=\{\(r\) => `\$\{r\.symbol\}-\$\{r\.date\}`\} columns=\{columns\} stack phonePage=\{10\} \/>/);
  for (const h of ["Company", "Market value", "Price now", '"Day"', "Revenue, a year on", "Profit, a year on", "Past results-day moves", "Options imply", "Meeting"])
    assert.ok(page.includes(`header: ${h.startsWith('"') ? h : `"${h}"`}`), h);
  assert.doesNotMatch(page, /className="inv-row"/);        // no chips and no two uneven columns
  assert.doesNotMatch(page, /k-cols/);
});

const filters = read("src/components/CalendarFilters.tsx");
const quotes = read("src/lib/rowQuotes.ts");
const corp = read("src/pages/CorpActionsPage.tsx");

test("RES-1: the filters are size, sector, index, day, purpose, sort and F&O, with counts, kept on this device", () => {
  for (const label of ['label="Company size"', 'label="Index"', 'label="Day"', 'label="Sort by"', "F&amp;O stocks only"]) assert.ok(filters.includes(label), label);
  for (const label of ["Results only", "With other business", 'label="Meeting"']) assert.ok(page.includes(label), label);
  assert.match(page, /<CalendarFilters region=\{region\}/);
  assert.match(page, /keptFilters\(KEEP, NO_FILTERS\)/);
  assert.match(page, /keepFilters\(KEEP, filters\)/);
  assert.match(filters, /localStorage\.getItem\(key\)/);
  assert.match(filters, /localStorage\.setItem\(key, JSON\.stringify\(f\)\)/);
  assert.match(filters, /\$\{total\.toLocaleString\("en-IN"\)\} \$\{plural\(total\)\} · \$\{matching\.toLocaleString\("en-IN"\)\} shown/);
  assert.match(filters, /"Filters"\}\{active \? ` \(\$\{active\}\)` : ""\}/);          // a phone's "Filters (n)"
  assert.match(filters, /\{phone && <button/);
  assert.match(filters, /no market value kept yet, so a size can't place/);
});

test("RES-1: live prices, earlier moves and implied moves are read for the rows in view only, a few at a time", () => {
  assert.match(quotes, /export const LIVE_ROWS = 48;/);
  assert.match(page, /\.flatMap\(\(w\) => w\.rows\)\.slice\(0, LIVE_ROWS\)/);
  assert.match(quotes, /useMarketRefresh\(\[region\], read, symbols\.length > 0\)/);          // each minute while the market trades, never otherwise
  assert.match(quotes, /researchApi\.quotes\(region, syms\)/);
  assert.match(page, /useRowQuotes\(region, symbols\)/);
  assert.match(page, /i \+= 6\) \{/);
  assert.match(page, /i \+= 8\) \{/);
  assert.match(page, /\/research\/results\/moves\?region=/);
  assert.match(page, /\/research\/results\/implied\?symbols=/);
  assert.match(page, /Prices as of \$\{fmtTime\(quoteAt!/);
  assert.match(page, /Prices are each company's last close/);
});

test("RES-1: the corporate actions calendar is a table a day with the same filters and live prices", () => {
  assert.match(corp, /<DataTable label=\{`Corporate actions going ex on \$\{exDay\(d\)\}`\} rows=\{on\} rowKey=\{\(r\) => r\.id\} columns=\{columns\} stack phonePage=\{10\} \/>/);
  for (const h of ["Company", "Action", "Amount or ratio", "Record date", "Price now", "Yield of this payment", "Market value"]) assert.ok(corp.includes(`header: "${h}"`), h);
  assert.match(corp, /<CalendarFilters region=\{region\}/);
  assert.match(corp, /useRowQuotes\(region, symbols\)/);
  assert.match(corp, /Kind of action/);
  for (const sort of ["Ex-date, soonest first", "Market value, largest first", "Yield of the payment, highest first", "Company name"]) assert.ok(corp.includes(sort), sort);
  assert.doesNotMatch(corp, /inv-row|ActionLine/);
  assert.match(corp, /\(r\.amount \/ x\) \* 100/);          // a dividend's amount over the price now
  assert.match(corp, /The yield is one payment over the price now, not the year's\./);
});

test("RES-1: facts and arrows, never a view: no advice words on the page", () => {
  assert.doesNotMatch(page, /\b(buy|sell|should|accumulate|avoid|trade this)\b/i);
  assert.match(page, /\$\{v > 0 \? "▲" : v < 0 \? "▼" : ""\} \$\{Math\.abs\(v\)\.toFixed\(1\)\}%/);
  assert.match(page, /Facts, not a forecast\./);
});
