// TABLES EVERYWHERE (owner, 4 Nov: "make tables?" on /library's cards; "fix globally"): every page that listed comparable results
// as a grid of cards (the library signed in and out, the notebooks) is a table now, with sortable figure columns and a row's
// details one tap away. Swept over every page's source, so a new grid of result cards fails here.
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("../src/", import.meta.url).pathname;
const files = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? files(p) : p.endsWith(".tsx") ? [p] : []; });
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("no page lays out a list of strategies, runs or notebooks as a grid of cards", () => {
  for (const f of files(root)) {
    const src = readFileSync(f, "utf8");
    assert.doesNotMatch(src, /className="k-cards (lib|nb)-cards"|<LibraryCard\b/, f);
  }
});

test("the library (both) and the notebooks are DataTables; the library's figures sort and its rules open under the row", () => {
  const bits = read("src/components/LibraryBits.tsx");
  assert.match(bits, /<DataTable label=\{label\} rows=\{sorted\} rowKey=\{\(e\) => e\.id\} columns=\{cols\} stack/);
  assert.equal((bits.match(/numeric: true, sortable: true/g) ?? []).length, 5, "after costs, buy and hold, vs hold, worst fall, unseen period");
  assert.match(bits, /detail=\{\{ label: "Rules and details", render: details \}\}/);
  for (const f of ["src/pages/LibraryPage.tsx", "src/pages/PublicLibrary.tsx"]) assert.match(read(f), /<LibraryTable key=\{`[^`]*`\} rows=/, f);
  assert.match(read("src/pages/Home.tsx"), /<DataTable label="Your notebooks"/);
  // the table's details row: a button with aria-expanded after the row's name, the details in a row of their own across the table
  const dt = read("src/components/kit/DataTable.tsx");
  assert.match(dt, /className="k-detail-btn" aria-expanded=\{isOpen\} aria-controls=\{isOpen \? did : undefined\}/);
  assert.match(dt, /<tr id=\{did\} className=\{\["k-detail-row", attrs\.className\]/);
  assert.match(dt, /<td colSpan=\{columns\.length\}/);
});
