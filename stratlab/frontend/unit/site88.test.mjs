// site88 (Release 88), the owner's three asks that can be checked without a browser: sorting on every table header (lib/tableSort.ts and the
// kit DataTable), the holder's spellings as a compact folded table, no dates on the themes' chips.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parseNumber, parseDate, kindOf, valueOf, sortByValues, firstDesc, isBlank } from "../src/lib/tableSort.ts";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("numbers read back from what a cell shows: ₹, $, %, x, lakh cr, cr, bn, m, commas and the minus sign", () => {
  assert.equal(parseNumber("₹1,234.5"), 1234.5);
  assert.equal(parseNumber("−2.3%"), -2.3);
  assert.equal(parseNumber("-2.3%"), -2.3);
  assert.equal(parseNumber("+4.1%"), 4.1);
  assert.equal(parseNumber("▼ 1.2%"), -1.2);
  assert.equal(parseNumber("12.5x"), 12.5);
  assert.equal(parseNumber("₹1.2 lakh cr"), 1.2e12);
  assert.equal(parseNumber("₹3,400 cr"), 3.4e10);
  assert.equal(parseNumber("$3.4bn"), 3.4e9);
  assert.equal(parseNumber("$120m"), 1.2e8);
  assert.equal(parseNumber("₹−45 cr"), -4.5e8);
  assert.equal(parseNumber("3.91% · was 3.50%"), 3.91);
  assert.equal(parseNumber("Rank 3"), null);
  assert.equal(parseNumber("–"), null);
  assert.ok(parseNumber("₹1.2 lakh cr") > parseNumber("₹90,000 cr"));
});

test("days read back: 13 Nov 2026, 13 Nov (this year), ISO, Nov 2026, As of 30 Sep 2026", () => {
  assert.equal(parseDate("13 Nov 2026"), Date.UTC(2026, 10, 13));
  assert.equal(parseDate("13 Nov", 2026), Date.UTC(2026, 10, 13));
  assert.equal(parseDate("2026-11-13"), Date.UTC(2026, 10, 13));
  assert.equal(parseDate("Nov 2026"), Date.UTC(2026, 10, 1));
  assert.equal(parseDate("1 June 2026"), Date.UTC(2026, 5, 1));
  assert.equal(parseDate("As of 30 Sep 2026"), Date.UTC(2026, 8, 30));
  assert.equal(parseDate("Fri, 13 Nov"), Date.UTC(new Date().getFullYear(), 10, 13));
  assert.equal(parseDate("3 companies"), null);
  assert.equal(parseDate("Reliance Industries"), null);
});

test("a column's kind: numbers, days or words; blanks are no value", () => {
  assert.equal(kindOf(["₹1,200 cr", "–", "₹900 cr"]), "number");
  assert.equal(kindOf(["13 Nov 2026", "", "2 Oct 2026"]), "date");
  assert.equal(kindOf(["13 Nov 2026", "2 Oct 2026"], true), "date");
  assert.equal(kindOf(["Reliance", "TCS"]), "text");
  assert.equal(kindOf(["anything"], true), "number");
  assert.ok(isBlank("–") && isBlank("") && isBlank(" — ") && !isBlank("0"));
  assert.equal(firstDesc("number"), true);
  assert.equal(firstDesc("date"), true);
  assert.equal(firstDesc("text"), false);
});

test("sorting puts the blanks last both ways and keeps ties in their order", () => {
  const rows = ["a", "b", "c", "d", "e"];
  const texts = ["3%", "–", "−1%", "10%", "3%"];
  const v = texts.map((t) => valueOf(t, "number"));
  assert.deepEqual(sortByValues(rows, v, true), ["d", "a", "e", "c", "b"]);
  assert.deepEqual(sortByValues(rows, v, false), ["c", "a", "e", "d", "b"]);
  const words = ["beta", "", "Alpha", "gamma 10", "gamma 9"].map((t) => valueOf(t, "text"));
  assert.deepEqual(sortByValues(rows, words, false), ["c", "a", "e", "d", "b"]);
  const days = ["13 Nov 2026", "–", "2 Oct 2026", "1 Jan 2027", ""].map((t) => valueOf(t, "date"));
  assert.deepEqual(sortByValues(rows, days, true), ["d", "a", "c", "b", "e"]);
});

test("the kit table sorts every column by default: a header button with aria-sort, a phone's Sort by select, rows keep their own key", () => {
  const t = read("src/components/kit/DataTable.tsx");
  assert.match(t, /sort\?: \{ key: string; desc: boolean; onSort: \(key: string\) => void \} \| false;/);
  assert.match(t, /const autoOn = sort === undefined && !grid && !scrollEnd && rows\.length > 1;/);
  assert.match(t, /aria-sort=\{by \? \(on \? \(by\.desc \? "descending" : "ascending"\) : "none"\) : undefined\}/);
  assert.match(t, /<button type="button" className="k-th-hit" data-sort-key=\{c\.key\} aria-label=\{`Sort \$\{headText\(c\)\}`\} onClick=\{\(\) => onSort\(c\)\} \/>/);
  assert.match(t, /<span>Sort the table by<\/span>/);
  assert.match(t, /const sortCols = phone && !page && rows\.length >= 8 \? columns\.filter\(canSort\) : \[\];/);      // only a long list, only a phone
  assert.match(t, /import\("\.\.\/\.\.\/lib\/tableSort"\)/);      // loaded on the first sort, not with a page
  assert.match(t, /shown\.map\(\(\{ r, i: ri \}\) =>/);           // a row keeps its index, so its key and its open details go with it
  assert.doesNotMatch(t, /new ResizeObserver\(/);                 // R7T-014: watchSize
  assert.match(t, /watchSize\(b, /);
  // the opt-outs: where the order is the meaning
  for (const [p, re] of [["src/pages/trade/SignalsPage.tsx", /<DataTable sort=\{false\} label="Signal log"/], ["src/pages/money/NetWorthPage.tsx", /<DataTable sort=\{false\} label="The history's snapshots"/],
    ["src/pages/trade/EventsPage.tsx", /<DataTable label="The next seven days" sort=\{false\}/], ["src/components/ThemeDive.tsx", /<DataTable sort=\{false\} label="The theme's biggest companies by market value"/],
    ["src/pages/IpoPage.tsx", /<DataTable stack sort=\{false\} label=\{label\}/]]) assert.match(read(p), re, p);
});

test("the holder's spellings: a one-line fold opening a compact table, not a list of tick boxes", () => {
  const p = read("src/pages/HoldersPage.tsx");
  assert.doesNotMatch(p, /k-stack holder-names|Spellings counted as this holder \(untick/);
  assert.match(p, /<Disclosure className="holder-spellings" testId="holder-spellings"/);
  assert.match(p, /spellings counted as this holder` : `\$\{on\} of \$\{n\} spellings counted as this holder`\} · <span className="holder-spellings-review">Review<\/span>/);
  assert.match(p, /<DataTable label="Spellings counted as this holder" stack=\{false\}/);
  assert.match(p, /<span className="holder-spelling" title=\{x\.name\}>/);
  const css = read("src/styles.css");
  assert.match(css, /\.holder-spelling \{ display: block; max-width: min\(56ch, 60vw\); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; \}/);
});

test("themes: the Ready to open chips carry no date", () => {
  const p = read("src/pages/ThemesPage.tsx");
  assert.doesNotMatch(p, /theme-chip-day/);
  assert.doesNotMatch(read("src/styles.css"), /\.theme-chip-day/);
});
