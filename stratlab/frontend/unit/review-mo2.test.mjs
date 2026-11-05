// The owner's manual check of 25 Oct: no "New" tags anywhere, a Net worth page whose main action can be found, and My
// Holdings' recent filings in lined-up columns.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("MO-2: no page is tagged New (everything is new at launch)", () => {
  assert.doesNotMatch(read("src/lib/nav.ts"), /isNew|NEW_SINCE/);
  const tags = read("src/components/PageTags.tsx");
  assert.doesNotMatch(tags, />New</);
  assert.doesNotMatch(tags, /isNew/);
});

test("MO-2: Net worth: a full-size add button at the top and the usual kinds one tap away beside it", () => {
  const src = read("src/pages/money/NetWorthPage.tsx");
  assert.match(src, /actions=\{view \? <>\n\s*<button type="button" className="btn" onClick=\{\(\) => openAdd\(\)\}><Plus size=\{16\} \/>Add an entry<\/button>/);
  assert.doesNotMatch(src, /className="btn sm" onClick=\{\(\) => setAdding\(true\)\}>Add an entry/);
  assert.match(src, /const QUICK: Kind\[\] = \["cash", "fd", "epf", "ppf", "gold", "property", "loan"\]/);
  // owner, 5 Nov: the quick add is a menu beside "Add an entry", not a card of chips under the totals
  assert.match(src, /\{!full && <MoreMenu label="Quick add" buttonClass="btn quiet" items=\{\[/);
  assert.match(src, /\.\.\.QUICK\.map\(\(k\) => \(\{ label: FORM\[k\]\.title, icon: <Plus size=\{14\} \/>, run: \(\) => openAdd\(k\) \}\)\)/);
  assert.match(src, /\{ label: "Something else…", run: \(\) => openAdd\(\) \}/);
  assert.doesNotMatch(src, /<Card compact label="Add to your net worth">/);
  // a kind picked there opens its boxes straight away
  assert.match(src, /if \(k\) \{ setKind\(k\); setAddStart\(fresh\(k\)\); setStep\("form"\); \} else setStep\("pick"\);/);
});

test("MO-2: recent filings line up: date, tag and title in fixed grid columns", () => {
  assert.match(read("src/pages/HoldingsPage.tsx"), /<div key=\{i\} className="h-filing k-small">/);
  const css = read("src/styles.css");
  assert.match(css, /\.h-filing \{ display: grid; grid-template-columns: 7\.5em 17em minmax\(0, 1fr\); align-items: center;/);
});
