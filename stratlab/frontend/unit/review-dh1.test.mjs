// Review DH (25 Oct 2026): tax report, Tax tools, ITR export and the money calendar, the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DH-003, DH-006: the tax report leads with the year's total and what is payable with the interest", () => {
  const src = read("src/pages/TaxReportPage.tsx");
  const head = src.indexOf("<Headline y={y}");
  assert.ok(head > 0 && head < src.indexOf('title="Upload your trades"'));          // above the upload card
  assert.match(src, /Payable now, with interest/);
  assert.match(src, /data-testid="tax-payable-locked"/);
  assert.match(src, /as the return rounds it \(sections 288A and 288B\)/);
  assert.match(src, /y\.exemption\.used > 0 && <Meter/);                            // no blue sliver at ₹0
  assert.match(src, /const FIRST_SALES = 10;/);
});

test("DH-005, DH-007: the gains table shows the losses and adds up; F&O lines are exit lines", () => {
  const src = read("src/pages/TaxReportPage.tsx");
  assert.match(src, /Short-term losses this year/);
  assert.match(src, /foot=\{lossRows\.length \? \{ kind: "Net"/);
  assert.match(src, /header: "Exit lines"/);
  assert.doesNotMatch(src, /header: "Trades", numeric: true, cell: \(s\)/);
});

test("DH-012, DH-020, DH-021, DH-022: Tax tools' Form 67 date, the year still owing, the lock and the phone tabs", () => {
  const src = read("src/pages/money/TaxToolsPage.tsx");
  assert.doesNotMatch(src, /Form 67 before the return/);
  assert.match(src, /Form 67 by the end of the assessment year \(31 March \{y\.fy \+ 2\}; Rule 128\(9\)\)/);
  assert.match(src, /label="Tax still unpaid"/);
  assert.match(src, /data-testid="advance-owed-year"/);
  assert.match(src, /Taking off your TDS and payments, the amount still due by each date and the interest/);
  assert.match(src, /\["ltcg", "Long-term exemption", "Exemption"\]/);
  assert.match(src, /function PayableCard/);
});

test("DH-011: the ITR page lists what the return needs beyond its schedules", () => {
  const src = read("src/pages/money/ItrExportPage.tsx");
  assert.match(src, /data-testid="itr-not-covered"/);
  assert.match(src, /the ITR-2 and ITR-3 schedules they cover/);
});

test("DH-041, DH-042: own dates take plain rupees only, say each problem, refuse a twin; reminders off greys the rest", () => {
  const src = read("src/pages/money/MoneyCalendarPage.tsx");
  assert.match(src, /\/\^\\d\+\(\\\.\\d\{1,2\}\)\?\$\/\.test\(typed\)/);              // "1e3" isn't a number here
  const neg = src.indexOf("The amount can't be below 0");
  assert.ok(neg > 0 && neg < src.indexOf("Enter a date and a name"));               // the amount's problem is said first
  assert.match(src, /is already in your calendar on that date/);
  assert.match(src, /disabled=\{!rem\.on\} value=\{rem\.days\}/);
  assert.match(src, /checked=\{rem\.on && rem\.cats\.includes\(c\.id\)\} disabled=\{!rem\.on\}/);
  assert.match(src, /placeholder=\{`e\.g\. \$\{fmtDate\(parse\(addDays\(today, 30\)\)\)\}`\}/);
  assert.match(read("src/styles.css"), /\.mc-own > li\.mc-own-row \{ display: grid;/);
  assert.match(read("src/components/kit/DateInput.tsx"), /placeholder=\{placeholder\}/);
});

test("DH-041: the calendar's amount rule, run", () => {
  const rule = (s) => { const t = s.replace(/[,\s₹]/g, ""); return t ? (/^\d+(\.\d{1,2})?$/.test(t) ? Number(t) : /^[-−]/.test(t) ? -1 : NaN) : null; };
  assert.equal(rule("2,50,000"), 250000);
  assert.ok(Number.isNaN(rule("1e3")));
  assert.equal(rule("−500"), -1);
  assert.equal(rule("-500"), -1);
  assert.equal(rule(""), null);
});
